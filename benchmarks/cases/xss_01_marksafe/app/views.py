from django.utils.safestring import mark_safe


def render_name(request):
    return mark_safe(request.GET.get("name", ""))
