import courseware
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from lti_provider.signature_validator import SignatureValidator
from django.contrib.auth.views import redirect_to_login
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required


REQUIRED_PARAMETERS = [
    'roles', 'context_id', 'oauth_version', 'oauth_consumer_key',
    'oauth_signature', 'oauth_signature_method', 'oauth_timestamp',
    'oauth_nonce'
    ]

LTI_SESSION_KEY = 'lti_provider_parameters'


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

    Authentication in this view is a little tricky, since clients use a POST
    with parameters to fetch it. We can't just use @login_required since in the
    case where a user is not logged in it will redirect back after login using a
    GET request, which would lose all of our LTI parameters.

    Instead, we verify the LTI launch in this view before checking if the user
    is logged in, and store the required LTI parameters in the session. Then we
    do the authentication check, and if login is required we redirect back to
    the lti_run view. If the user is already logged in, we just call that view
    directly.
    """
    if not settings.FEATURES["ENABLE_LTI_PROVIDER"]:
        return HttpResponseForbidden()

    # Check the OAuth signature on the message
    if not SignatureValidator().verify(request):
        return HttpResponseForbidden()

    params = get_required_parameters(request.POST)
    if not params:
        return HttpResponseBadRequest()
    # Store the course, chapter, section and position in the session to prevent
    # privilege escalation if a staff member in one course tries to access
    # material in another.
    params["course_id"] = course_id
    params["chapter"] = chapter
    params["section"] = section
    params["position"] = position
    request.session[LTI_SESSION_KEY] = params

    if not request.user.is_authenticated():
        run_url = reverse('lti_provider.views.lti_run')
        return redirect_to_login(run_url, settings.LOGIN_URL,
                                 REDIRECT_FIELD_NAME)

    return lti_run(request)


@login_required
def lti_run(request):
    """
    This method can be reached in two ways, and must always follow a POST to
    lti_launch:
     - The user was logged in, so this method was called by lti_launch
     - The user was not logged in, so the login process redirected them back here.

    In either case, the session was populated by lti_launch, so all the required
    LTI parameters will be stored there. Note that the request passed here may
    or may not contain the LTI parameters (depending on how the user got here),
    and so we should only use LTI parameters from the session.

    Users should never call this view directly; if a user attempts to call it
    without having first gone through lti_launch (and had the LTI parameters
    stored in the session) they will get a 403 response.
    """

    # Check the parameters to make sure that the session is associated with a
    # valid LTI launch
    params = restore_params_from_session(request)
    if not params:
        # This view has been called without first setting the session
        return HttpResponseForbidden()
    # Remove the parameters from the session to prevent replay
    del request.session[LTI_SESSION_KEY]

    return render_courseware(params)


def get_required_parameters(dictionary, additional_params=[]):
    """
    Extract all required LTI parameters from a dictionary and verify that none
    are missing.

    :return: A dictionary of all required parameters from the dictionary, or
             None if any parameters are missing.
    """
    params = {}
    for key in REQUIRED_PARAMETERS + additional_params:
        if key not in dictionary:
            return None
        params[key] = dictionary[key]
    return params


def restore_params_from_session(request):
    """
    Fetch the parameters that were stored in the session by an LTI launch, and
    verify that all required parameters are present. Missing parameters could
    indicate that a user has directly called the lti_run endpoint, rather than
    going through the LTI launch.

    :return: A dictionary of all LTI parameters from the session, or None if
             any parameters are missing.
    """
    session_params = request.session[LTI_SESSION_KEY]
    additional_params = ['course_id', 'chapter', 'section', 'position']
    return get_required_parameters(session_params, additional_params)


def render_courseware(lti_params):
    """
    Render the content requested for the LTI launch.

    TODO: This method depends on the current refactoring work on the
    courseware/courseware.html template. It's signature may change depending on
    the requirements for that template once the refactoring is complete.

    :return: an HttpResponse object that contains the template and necessary
    context to render the courseware.
    """
    return HttpResponse("TODO: Render refactored courseware view " + str(lti_params))
