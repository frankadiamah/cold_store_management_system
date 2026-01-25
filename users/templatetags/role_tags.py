
from django import template

register = template.Library()

@register.simple_tag
def is_super_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter
    (name="SuperAdmin").exists())

# register = template.Library()

# @register.simple_tag(takes_context=True)
# def user_has_role(context, user, role):
#     return user.groups.filter(name=role).exists()