document.getElementById('repo-form').addEventListener('submit', async function(event) {
    event.preventDefault();
    const repoUrl = document.getElementById('repo-url').value;
    const loadingDiv = document.getElementById('loading');
    const resultDiv = document.getElementById('result');
    const analysisOutput = document.getElementById('analysis-output');
    const readmeSection = document.getElementById('readme-section');
    const readmeContent = document.getElementById('readme-content');
    const gitlabSection = document.getElementById('gitlab-section');
    const gitlabLink = document.getElementById('gitlab-link');

    loadingDiv.style.display = 'block';
    resultDiv.style.display = 'none';
    readmeSection.style.display = 'none';
    gitlabSection.style.display = 'none';

    try {
        const response = await fetch('/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_url: repoUrl })
        });

        const result = await response.json();

        if (response.ok) {
            analysisOutput.textContent = JSON.stringify(result.analysis_result, null, 2);
            resultDiv.style.display = 'block';

            readmeContent.innerHTML = marked(result.readme_content);
            readmeSection.style.display = 'block';

            if (result.gitlab_url) {
                gitlabLink.href = result.gitlab_url;
                gitlabLink.textContent = result.gitlab_url;
                gitlabSection.style.display = 'block';
            }
        } else {
            analysisOutput.textContent = `Error: ${result.error}`;
            resultDiv.style.display = 'block';
        }
    } catch (error) {
        analysisOutput.textContent = `Error: ${error.message}`;
        resultDiv.style.display = 'block';
    } finally {
        loadingDiv.style.display = 'none';
    }
});