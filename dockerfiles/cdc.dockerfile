FROM python:3.12

WORKDIR /app
COPY dist/neph-*-py3-none-any.whl .
RUN pip install *.whl
CMD ["neph", "cdc"]

