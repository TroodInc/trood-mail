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
    
    SECRET_KEY = values.Values(
        '3@a)-cbt514^!a%qiotx$su4%29p@dxfrd-qb(oouzbp^@!+gr', environ_prefix=''
    )

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

    MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
    MEDIA_URL = '/media/'

    SKIP_MAILS_BEFORE = datetime.strptime(
        values.Values("01-01-2018", environ_prefix=''), "%d-%m-%Y"
    ).date()

    DEFAULT_IMAP_QUERY = values.Values("NEW", environ_prefix='')

    # @todo: replace with configurable app from TroodLib
    GLOBAL_CONFIGURABLE = {
        "PUBLIC_URL": values.Values('', environ_prefix='')
    }

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

    TROOD_AUTH_SERVICE_URL = values.URLValue('http://authorization.trood:8000/', environ_prefix='')

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

    TROOD_ABAC = {
        'RULES_SOURCE': values.Values('URL', environ_prefix=''),
        'RULES_PATH': values.Values("f{TROOD_AUTH_SERVICE_URL}api/v1.0/abac/", environ_prefix='')
    }

    # FIXME: must be setupable
    RAVEN_CONFIG = {
        'dsn': 'http://30386ed35c72421c92d3fc14a0e8a1f3:ef714492b6574c83b5e96a70a129b34a@sentry.dev.trood.ru/3',
        'release': 'dev'
    }

    SERVICE_DOMAIN = values.Values("MAIL", environ_prefix='')
    SERVICE_AUTH_SECRET = values.Values("SERVICE_AUTH_SECRET", environ_prefix='')

    DEFAULT_FILE_STORAGE = 'mail.api.storage.TroodFileStorage'
    DEFAULT_FILE_STORAGE_HOST = 'http://fileservice:8000/'


class Production(BaseConfiguration):
    DEBUG = False

    TROOD_AUTH_SERVICE_URL = values.URLValue('http://authorization.trood:8000/', environ_prefix='')

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

    TROOD_ABAC = {
        'RULES_SOURCE': values.Value("URL", environ_prefix=''),
        'RULES_PATH': values.Value("f{TROOD_AUTH_SERVICE_URL}api/v1.0/abac/", environ_prefix='')
    }
    # FIXME: must be setupable
    RAVEN_CONFIG = {
        'dsn': 'http://30386ed35c72421c92d3fc14a0e8a1f3:ef714492b6574c83b5e96a70a129b34a@sentry.dev.trood.ru/3',
        'release': 'prod'
    }

    SERVICE_DOMAIN = values.Value("MAIL", environ_prefix='')
    SERVICE_AUTH_SECRET = values.Value('', environ_prefix='')

    DEFAULT_FILE_STORAGE = 'mail.api.storage.TroodFileStorage'
    DEFAULT_FILE_STORAGE_HOST = 'http://fileservice:8000/'


class Test(BaseConfiguration):
    DEBUG = True
