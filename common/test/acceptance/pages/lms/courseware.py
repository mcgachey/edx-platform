"""
Courseware page.
"""

from .course_page import CoursePage
from selenium.webdriver.common.action_chains import ActionChains


class CoursewarePage(CoursePage):
    """
    Course info.
    """

    url_path = "courseware/"
    xblock_component_selector = '.vert .xblock'
    section_selector = '.chapter'
    subsection_selector = '.chapter ul li'

    def is_browser_on_page(self):
        return self.q(css='body.courseware').present

    @property
    def num_sections(self):
        """
        Return the number of sections in the sidebar on the page
        """
        return len(self.q(css=self.section_selector))

    @property
    def num_subsections(self):
        """
        Return the number of subsections in the sidebar on the page, including in collapsed sections
        """
        return len(self.q(css=self.subsection_selector))

    @property
    def xblock_components(self):
        """
        Return the xblock components within the unit on the page.
        """
        return self.q(css=self.xblock_component_selector)

    @property
    def num_xblock_components(self):
        """
        Return the number of rendered xblocks within the unit on the page
        """
        return len(self.xblock_components)

    def xblock_component_type(self, index=0):
        """
        Extract rendered xblock component type.

        Returns:
            str: xblock module type
            index: which xblock to query, where the index is the vertical display within the page
                (default is 0)
        """
        return self.q(css=self.xblock_component_selector).attrs('data-block-type')[index]

    def xblock_component_html_content(self, index=0):
        """
        Extract rendered xblock component html content.

        Returns:
            str: xblock module html content
            index: which xblock to query, where the index is the vertical display within the page
                (default is 0)

        """
        return self.q(css=self.xblock_component_selector).attrs('innerHTML')[index].strip()

    def xblock_components_contain_text(self, expected_components_text):
        """
        Iterates through all xblock components on the page and verifies that each
        contains its expected text (note that they can also contain additional text).

        Return False if either there are an incorrect number of components on the page,
        or at least one of them does not contain the expected text
        """
        components = self.xblock_components
        if len(expected_components_text) != len(components):
            return False
        for index, expected_text in enumerate(expected_components_text):
            if expected_text not in components[index].text:
                return False
        return True

    def tooltips_displayed(self):
        """
        Verify if sequence navigation bar tooltips are being displayed upon mouse hover.
        """
        for index, tab in enumerate(self.q(css='#sequence-list > li')):
            ActionChains(self.browser).move_to_element(tab).perform()
            if not self.q(css='#tab_{index} > p'.format(index=index)).visible:
                return False

        return True
