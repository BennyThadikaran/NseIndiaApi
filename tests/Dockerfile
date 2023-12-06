FROM python:3.8.18-slim-bullseye

WORKDIR /app

RUN pip install requests mthrottle

RUN mkdir nse

RUN echo 'from nse import NSE\nwith NSE("./") as nse:\n\tprint(nse.status())' > test.py

COPY nse/ nse/
COPY __init__.py .

CMD ["python3", "test.py"]
