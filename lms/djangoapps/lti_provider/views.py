import courseware
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from lti_provider.signature_validator import SignatureValidator
from django.contrib.auth.decorators import login_required


def lti_launch(request, course_id, chapter=None, section=None, position=None):
    """
    Endpoint for all requests to embed edX content via the LTI protocol. This
    endpoint will be called by a POST message that contains the parameters for
    an LTI launch (we support version 1.2 of the LTI specification):
        http://www.imsglobal.org/lti/ltiv1p2/ltiIMGv1p2.html

    An LTI launch is successful if:
        - The launch contains all the required parameters
        - The launch data is correctly signed using a known client key/secret pair
        - The user is logged into the edX instance
    """
    if not settings.FEATURES["ENABLE_LTI_PROVIDER"]:
        return HttpResponseForbidden()

    if not check_required_parameters(request):
        return HttpResponseBadRequest()

    # Check the OAuth signature on the message
    if not SignatureValidator().verify(request):
        return HttpResponseForbidden()

    return render_courseware(course_id, chapter, section, position)


def check_required_parameters(request):
    """
    Check that the POST request contains all of the required parameters for
    the LTI launch.

    :return: True if all required parameters are part of the POST request,
             False if any parameters are missing.
    """
    required = ['roles', 'context_id', 'oauth_version',
                'oauth_consumer_key', 'oauth_signature',
                'oauth_signature_method', 'oauth_timestamp',
                'oauth_nonce']
    for key in required:
        if key not in request.POST:
            return False
    return True


def render_courseware(course_id, chapter, section, position):
    """
    Render the content requested for the LTI launch.

    TODO: This method depends on the current refactoring work on the
    courseware/courseware.html template. It's signature may change depending on
    the requirements for that template once the refactoring is complete.

    :return: an HttpResponse object that contains the template and necessary
    context to render the courseware.
    """
    return HttpResponse("TODO: Render refactored courseware view")
