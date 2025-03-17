from django import template

register = template.Library()

@register.filter
def index(lst, i):
    """Returns the item at index i in the list."""
    try:
        return lst[i]
    except (IndexError, TypeError):
        return None

@register.filter
def attr(obj, attr_name):
    """Returns the attribute of an object."""
    try:
        return getattr(obj, attr_name)
    except (AttributeError, TypeError):
        return None