"""
Asynchronous tasks for the LTI provider app.
"""

from django.core.exceptions import ObjectDoesNotExist
from django.dispatch import receiver
import logging

from courseware.models import SCORE_CHANGED
from courseware.module_render import get_module_by_usage_id
from lms import CELERY_APP
from lti_provider.models import GradedAssignment
import lti_provider.outcomes
from lti_provider.views import parse_course_and_usage_keys
from xmodule.modulestore.django import modulestore

log = logging.getLogger("edx.lti_provider")




@CELERY_APP.task
def send_outcome(points_possible, points_earned, user_id, course_id, usage_id):
    """
    Calculate the score for a given user in a problem and send it to the
    appropriate LTI consumer's outcome service.
    """
    if points_earned is None or not points_possible:
        log.error(
            "Outcome Service: Invalid Points earned (%s) or points possible (%s)",
            points_earned, points_possible
        )
        return
    if points_earned > points_possible:
        log.error(
            "Outcome Service: Points earned (%s) can't be more than points possible (%s)",
            points_earned, points_possible
        )
        return

    course_key, usage_key = parse_course_and_usage_keys(course_id, usage_id)
    if not all((course_key, usage_key)):
        log.error(
            "Outcome Service: Invalid course ID (%s) or usage ID (%s)",
            course_id, usage_id
        )
        return


    descriptor = modulestore().get_item(usage_key)


    # module, _dummy = get_module_by_usage_id(
    #     request,
    #     unicode(course_key),
    #     unicode(usage_key)
    # )
    #
    parent = descriptor.get_parent()
    print "{}".format(descriptor.location)
    while parent:
        print "Parent: {}".format(parent.location)
        parent = parent.get_parent()


    try:
        assignment = GradedAssignment.objects.get(
            user=user_id, course_key=course_key, usage_key=usage_key
        )
    except ObjectDoesNotExist:
        # The user/course/usage combination does not relate to a previous graded
        # LTI launch. This can happen if an LTI consumer embeds some gradable
        # content in a context that doesn't require a score (maybe by including
        # an exercise as a sample that students may complete but don't count
        # towards their grade).
        return

    # Calculate the user's score, on a scale of 0.0 - 1.0.
    if points_possible == 0:
        score = 0.0
    else:
        score = float(points_earned) / float(points_possible)

    xml = lti_provider.outcomes.generate_replace_result_xml(assignment.lis_result_sourcedid, score)
    try:
        response = lti_provider.outcomes.sign_and_send_replace_result(assignment, xml)
    except ObjectDoesNotExist:
        # failed to send result. 'response' is None, so the error will be logged
        # at the end of the method.
        pass

    # If something went wrong, make sure that we have a complete log record.
    # That way we can manually fix things up on the campus system later if
    # necessary.
    if not (response and lti_provider.outcomes.check_replace_result_response(response)):
        log.error(
            "Outcome Service: Failed to update score on LTI consumer. "
            "User: %s, course: %s, usage: %s, score: %s, possible: %s "
            "status: %s, body: %s",
            user_id,
            course_key,
            usage_key,
            points_earned,
            points_possible,
            response,
            response.text
        )
