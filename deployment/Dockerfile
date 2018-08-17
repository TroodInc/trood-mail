FROM python:3

ENV APPDIR=/home/src
ENV PYTHONPATH=$PYTHONPATH:$APPDIR

RUN apt-get update && \
    apt-get install gcc g++ make libffi-dev libssl-dev -y && mkdir -p $APPDIR

WORKDIR $APPDIR

COPY ./mail $APPDIR/mail
COPY ./manage.py $APPDIR/
COPY ./requirements.txt $APPDIR/
COPY ./pytest.ini $APPDIR/

RUN pip install -r $APPDIR/requirements.txt

EXPOSE 8000
CMD /usr/local/bin/gunicorn -w 4 -b 0.0.0.0:8000 --reload --access-logfile - mail.wsgi:application