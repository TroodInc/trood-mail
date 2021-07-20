FROM python:3.6

ENV APPDIR=/home/src
ENV PYTHONPATH=$PYTHONPATH:$APPDIR

RUN apt-get update && \
    apt-get install gcc g++ make libffi-dev libssl-dev -y && mkdir -p $APPDIR

WORKDIR $APPDIR

COPY ./mail $APPDIR/mail
COPY ./manage.py $APPDIR/
COPY ./requirements.txt $APPDIR/
COPY ./docs/_static/swagger.yml $APPDIR/static/
COPY ./pytest.ini $APPDIR/

RUN pip install --upgrade -r $APPDIR/requirements.txt

EXPOSE 8000
CMD /usr/local/bin/gunicorn -b 0.0.0.0:8000 --reload --access-logfile - mail.wsgi:application