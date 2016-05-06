from distutils.version import LooseVersion
from django import template
from django.utils.version import get_version


register = template.Library()

if LooseVersion(get_version()) >= LooseVersion('1.9'):
    JQUERY_PATH = 'admin/js/vendor/jquery/jquery.js'

    # `assignment_tag` is deprecated as of 1.9, `simple_tag` should be used
    tag_decorator = register.simple_tag
else:
    JQUERY_PATH = 'admin/js/jquery.js'
    tag_decorator = register.assignment_tag


@register.assignment_tag
def get_jquery_path():
    return JQUERY_PATH
