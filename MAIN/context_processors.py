from .views import get_active_announcement

def announcement_processor(request):
    """
    Context processor to make the active announcement available in all templates
    """
    return {
        'announcement': get_active_announcement()
    }