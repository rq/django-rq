from django import template

register = template.Library()


@register.simple_tag
def get_jquery_path() -> str:
    return 'admin/js/vendor/jquery/jquery.js'
