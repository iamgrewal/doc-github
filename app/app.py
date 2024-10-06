import os
import sys
import subprocess
import shutil
import logging
import requests
from git import Repo, GitError
from dotenv import load_dotenv
import argparse
import concurrent.futures
from urllib.parse import quote, urlparse
import urllib.parse
from flask import Flask, render_template, request, jsonify

# Load environment variables from .env file
load_dotenv()
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
SONAR_TOKEN = os.getenv('SONAR_TOKEN')
GITLAB_TOKEN = os.getenv('GITLAB_TOKEN')
GITLAB_URL = os.getenv('GITLAB_URL', 'https://gitlab.com')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

def check_sonarqube_availability(sonar_host_url):
    try:
        response = requests.get(f"{sonar_host_url}/api/system/status", timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False

def check_sonarscanner_availability():
    try:
        subprocess.run(["sonar-scanner", "-v"], check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        return False

def perform_code_analysis(repo_path, repo_name, sonar_host_url):
    """
    Perform code analysis using SonarQube on the specified repository.

    Args:
        repo_path (str): The local path to the cloned repository.
        repo_name (str): The name of the repository.
        sonar_host_url (str): The URL of the SonarQube server.

    Returns:
        dict: A dictionary containing the status and analysis results.
    """
    logging.info('Performing code analysis on %s with SonarQube...', repo_name)
    
    if not check_sonarscanner_availability():
        logging.error("sonar-scanner is not available. Please install it and add it to your PATH.")
        return {'status': 'Code analysis failed.', 'error': 'sonar-scanner not available'}
    
    if not check_sonarqube_availability(sonar_host_url):
        logging.error("SonarQube server is not accessible at %s", sonar_host_url)
        return {'status': 'Code analysis failed.', 'error': 'SonarQube server not accessible'}
    
    try:
        # Create a unique project key
        project_key = quote(f"{os.getenv('GITHUB_USERNAME', 'default')}/{repo_name}", safe='')
        
        # Run SonarScanner
        sonar_scanner_cmd = [
            "sonar-scanner",
            f"-Dsonar.projectKey={project_key}",
            f"-Dsonar.sources={repo_path}",
            f"-Dsonar.host.url={sonar_host_url}",
            f"-Dsonar.login={SONAR_TOKEN}"
        ]
        subprocess.run(sonar_scanner_cmd, check=True)

        # Fetch analysis results from SonarQube API
        sonar_api_url = f"{sonar_host_url}/api/issues/search?projectKeys={project_key}"
        response = requests.get(sonar_api_url, auth=(SONAR_TOKEN, ''), timeout=30)
        response.raise_for_status()
        issues = response.json().get('issues', [])

        return {'status': 'Code analysis completed successfully.', 'issues': issues}
    except subprocess.CalledProcessError as e:
        logging.error("SonarQube analysis failed for %s: %s", repo_name, str(e))
        return {'status': 'Code analysis failed.', 'error': str(e)}
    except requests.RequestException as e:
        logging.error("Failed to fetch SonarQube results for %s: %s", repo_name, str(e))
        return {'status': 'Failed to fetch analysis results.', 'error': str(e)}

def extract_readme(repo_path):
    """
    Extract the content of README.md from the repository.

    Args:
        repo_path (str): The local path to the cloned repository.

    Returns:
        str: The content of README.md or a message if not found.
    """
    readme_path = os.path.join(repo_path, 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as file:
            return file.read()
    else:
        return 'README.md not found.'

def process_repository(repo, clone_directory, sonar_host_url, github_token):
    repo_name = repo["name"]
    clone_url = repo["clone_url"]
    is_private = repo["private"]
    repo_path = os.path.join(clone_directory, repo_name)

    logging.info("Processing repository: %s", repo_name)

    try:
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)
        
        # Modify clone URL to include the token for private repositories
        if is_private:
            parsed_url = urllib.parse.urlparse(clone_url)
            auth_url = parsed_url._replace(
                netloc=f"{urllib.parse.quote(github_token)}@{parsed_url.netloc}"
            )
            auth_clone_url = urllib.parse.urlunparse(auth_url)
        else:
            auth_clone_url = clone_url

        # Clone the repository
        Repo.clone_from(auth_clone_url, repo_path)
        logging.info("Successfully cloned %s.", repo_name)

        analysis_result = perform_code_analysis(repo_path, repo_name, sonar_host_url)
        readme_content = extract_readme(repo_path)

        logging.info("Analysis result for %s: %s", repo_name, analysis_result)
        logging.info("README content for %s:\n%s", repo_name, readme_content)

        # Uncomment the next line to delete the cloned repository after processing
        # shutil.rmtree(repo_path)

    except GitError as e:
        logging.error("Git error while cloning %s: %s", repo_name, str(e))
    except (subprocess.CalledProcessError, requests.RequestException) as e:
        logging.error("Error during analysis or fetching results for %s: %s", repo_name, str(e))
    except Exception as e:
        logging.error("Unexpected error with %s: %s", repo_name, str(e))
        logging.exception("Detailed traceback:")

def push_to_gitlab(repo_path, repo_name, github_url):
    """
    Push the analyzed repository to GitLab.

    Args:
        repo_path (str): The local path to the cloned repository.
        repo_name (str): The name of the repository.
        github_url (str): The original GitHub URL of the repository.

    Returns:
        str: The URL of the new GitLab repository.
    """
    try:
        # Parse the GitHub URL to get the user/org name
        parsed_url = urlparse(github_url)
        path_parts = parsed_url.path.strip('/').split('/')
        github_user = path_parts[0]

        # Create a new repository on GitLab
        gitlab_api_url = f"{GITLAB_URL}/api/v4/projects"
        headers = {'PRIVATE-TOKEN': GITLAB_TOKEN}
        data = {
            'name': repo_name,
            'visibility': 'private'  # You can change this to 'public' if needed
        }
        response = requests.post(gitlab_api_url, headers=headers, json=data)
        response.raise_for_status()
        gitlab_repo_info = response.json()

        # Set up the new remote for the local repository
        repo = Repo(repo_path)
        gitlab_remote_url = gitlab_repo_info['http_url_to_repo'].replace('https://', f'https://oauth2:{GITLAB_TOKEN}@')
        origin = repo.create_remote('gitlab', url=gitlab_remote_url)

        # Push to the new GitLab repository
        origin.push('master')

        return gitlab_repo_info['web_url']
    except Exception as e:
        logging.error(f"Error pushing to GitLab: {str(e)}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_repo():
    repo_url = request.json['repo_url']
    
    # Extract repo name from URL
    repo_name = repo_url.split('/')[-1].replace('.git', '')
    
    clone_directory = 'temp_repos'
    os.makedirs(clone_directory, exist_ok=True)
    repo_path = os.path.join(clone_directory, repo_name)

    try:
        # Clone and analyze the repository
        process_repository({'name': repo_name, 'clone_url': repo_url, 'private': False}, clone_directory, 'http://localhost:9000', GITHUB_TOKEN)
        
        # Perform the analysis
        analysis_result = perform_code_analysis(repo_path, repo_name, 'http://localhost:9000')
        
        # Push to GitLab
        gitlab_url = push_to_gitlab(repo_path, repo_name, repo_url)
        
        # Read README content
        readme_content = extract_readme(repo_path)

        # Clean up
        shutil.rmtree(repo_path)

        return jsonify({
            'analysis_result': analysis_result,
            'readme_content': readme_content,
            'gitlab_url': gitlab_url
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)