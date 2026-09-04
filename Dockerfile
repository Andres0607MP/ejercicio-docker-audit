FROM python:3.8
WORKDIR /app

COPY . /app

RUN pip install Flask==1.1.2 PyMySQL==0.9.3

EXPOSE 5050
CMD ["python", "app.py"]