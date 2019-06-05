import glob
import importlib
from datetime import datetime
import dj_database_url

import os

from configurations import Configuration, values


# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BaseConfiguration(Configuration):
    # Django environ
    # FIXME: we must have oportunity upload settings from env file
    # DOTENV = os.path.join(BASE_DIR, '.env')
    
    # SECURITY WARNING: keep the secret key used in production secret!
    
    SECRET_KEY = '3@a)-cbt514^!a%qiotx$su4%29p@dxfrd-qb(oouzbp^@!+gr'

    # FIXME: we must setup that list
    ALLOWED_HOSTS = ['*']

    INSTALLED_APPS = [
        'django.contrib.admin',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.staticfiles',
        'raven.contrib.django.raven_compat',
        'rest_framework',
        'django_filters',
        'django_mailbox',

        'mail.api',
    ]

    MIDDLEWARE = [
        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
    ]

    ROOT_URLCONF = 'mail.urls'

    TEMPLATES = [
        {
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': [],
            'APP_DIRS': True,
            'OPTIONS': {
                'builtins': ['mail.api.templatetags.trood'],
                'context_processors': [
                    'django.template.context_processors.debug',
                    'django.template.context_processors.request',
                    'django.contrib.auth.context_processors.auth',
                    'django.contrib.messages.context_processors.messages',
                ],
            },
        },
    ]

    WSGI_APPLICATION = 'mail.wsgi.application'

    DATABASES = {
        'default': dj_database_url.config(
            default='postgres://mail:mail@mail_postgres/mail'
        )
    }

    LOGGING = {
        'version': 1,
        'disable_existing_loggers': True,
        'root': {
            'level': 'WARNING',
            'handlers': ['sentry'],
        },
        'formatters': {
            'verbose': {
                'format': '%(levelname)s %(asctime)s %(module)s '
                          '%(process)d %(thread)d %(message)s'
            },
        },
        'handlers': {
            'sentry': {
                'level': 'WARNING',  # To capture more than ERROR, change to WARNING, INFO, etc.
                'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler',
                'tags': {'custom-tag': 'x'},
            },
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose'
            }
        },
        'loggers': {
            'django.db.backends': {
                'level': 'ERROR',
                'handlers': ['console'],
                'propagate': False,
            },
            'raven': {
                'level': 'DEBUG',
                'handlers': ['console'],
                'propagate': False,
            },
            'sentry.errors': {
                'level': 'DEBUG',
                'handlers': ['console'],
                'propagate': False,
            },
        },
    }

    # Internationalization
    # https://docs.djangoproject.com/en/1.11/topics/i18n/

    LANGUAGE_CODE = 'en-us'

    TIME_ZONE = 'UTC'

    USE_I18N = True

    USE_L10N = True

    USE_TZ = True

    TROOD_AUTH_SERVICE_URL = os.environ.get('TROOD_AUTH_SERVICE_URL', 'http://authorization.trood:8000/')

    REST_FRAMEWORK = {
        'DEFAULT_AUTHENTICATION_CLASSES': (),
        'DEFAULT_PERMISSION_CLASSES': (),
        'DEFAULT_FILTER_BACKENDS': (
            'django_filters.rest_framework.DjangoFilterBackend',
            'rest_framework.filters.SearchFilter',
            'mail.api.filters.ForceAdditionalOrderingFilter',
        ),
        'PAGE_SIZE': 10
    }

    TROOD_ABAC = {
        'RULES_SOURCE': os.environ.get("ABAC_RULES_SOURCE", "URL"),
        'RULES_PATH': os.environ.get("ABAC_RULES_PATH", "{}api/v1.0/abac/".format(TROOD_AUTH_SERVICE_URL))
    }


    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
    MEDIA_URL = '/media/'

    SKIP_MAILS_BEFORE = datetime.strptime(
        os.environ.get('SKIP_MAILS_BEFORE', '01-01-2018'), "%d-%m-%Y"
    ).date()

    DEFAULT_IMAP_QUERY =  os.environ.get('DEFAULT_IMAP_QUERY', "NEW")

    # @todo: replace with configurable app from TroodLib
    GLOBAL_CONFIGURABLE = {
        "PUBLIC_URL": os.environ.get('PUBLIC_URL')
    }

    ENABLE_RAVEN = os.environ.get('ENABLE_RAVEN', "False")

    if ENABLE_RAVEN == "True":
        RAVEN_CONFIG = {
            'dsn': os.environ.get('RAVEN_CONFIG_DSN'),
            'release': os.environ.get('RAVEN_CONFIG_RELEASE')
        }


    SERVICE_DOMAIN = os.environ.get("SERVICE_DOMAIN", "MAIL")
    SERVICE_AUTH_SECRET = os.environ.get("SERVICE_AUTH_SECRET")

    DEFAULT_FILE_STORAGE = 'mail.api.storage.TroodFileStorage'
    DEFAULT_FILE_STORAGE_HOST = 'http://fileservice:8000/'


    @classmethod
    def post_setup(cls):
        event_handlers = [module[:-3].replace("/", ".") for module in glob.glob('mail/events/*.py')]
        for handler in event_handlers:
            importlib.import_module(handler)


class Development(BaseConfiguration):
    DEBUG = True

    MIDDLEWARE = BaseConfiguration.MIDDLEWARE + [
        'trood_auth_client.middleware.TroodABACMiddleware',
    ]
    
    REST_FRAMEWORK = {
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'trood_auth_client.authentication.TroodTokenAuthentication',
        ),
        'DEFAULT_PERMISSION_CLASSES': (
            'rest_framework.permissions.IsAuthenticated',
            'trood_auth_client.permissions.TroodABACPermission',
        ),
        'DEFAULT_FILTER_BACKENDS': (
            'trood_auth_client.filter.TroodABACFilterBackend',
            'django_filters.rest_framework.DjangoFilterBackend',
            'rest_framework.filters.SearchFilter',
            'mail.api.filters.ForceAdditionalOrderingFilter',
        ),
        'PAGE_SIZE': 10
    }

class Production(BaseConfiguration):
    DEBUG = False

    REST_FRAMEWORK = {
        'DEFAULT_AUTHENTICATION_CLASSES': (
            'trood_auth_client.authentication.TroodTokenAuthentication',
        ),
        'DEFAULT_PERMISSION_CLASSES': (
            'rest_framework.permissions.IsAuthenticated',
            'trood_auth_client.permissions.TroodABACPermission',
        ),
        'DEFAULT_FILTER_BACKENDS': (
            'trood_auth_client.filter.TroodABACFilterBackend',
            'django_filters.rest_framework.DjangoFilterBackend',
            'rest_framework.filters.SearchFilter',
            'mail.api.filters.ForceAdditionalOrderingFilter',
        ),
        'PAGE_SIZE': 10
    }

class Test(BaseConfiguration):
    DEBUG = True
