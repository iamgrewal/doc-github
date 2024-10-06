FROM python:3.9

WORKDIR /app

COPY requirements.txt .

# Display the contents of requirements.txt
RUN echo "Contents of requirements.txt:" && cat requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV GITHUB_TOKEN=""
ENV SONAR_TOKEN=""

EXPOSE 5000

CMD ["python", "app/app.py"]
