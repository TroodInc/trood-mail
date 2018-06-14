from fabric.api import task
from fabric.context_managers import lcd
from fabric.operations import local

@task
def build():
    with lcd('./deployment/'):
        local('docker-compose build')
        local('docker-compose up -d')

@task
def test():
    with lcd('./deployment/'):
        local('docker-compose exec mail pytest')


@task
def cleanup():
    with lcd('./deployment/'):
        local('docker-compose down')