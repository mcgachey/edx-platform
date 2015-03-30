from django.http import HttpResponse


def lti_launch(request, course_id, chapter=None, section=None, position=None):
    return HttpResponse("TODO: Render refactored courseware view")
