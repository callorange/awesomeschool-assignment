"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

Importing this module initializes Django. config.settings loads the
repository-root .env and gives process environment variables priority.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
