import unittest

import make_site


class OperationsMenuTests(unittest.TestCase):
    def test_generated_pages_keep_all_seating_links(self):
        fixture = '''<style>body { margin:0; }</style>
        <section class="tab-groups"><button class="tab-button" type="button" data-tab="new-league">累計</button>
        <button class="tab-button" type="button" data-tab="new-season-6">シーズン6</button></section>
        <section class="tab-panel" id="panel-new-league"><p>cumulative</p></section>
        <section class="tab-panel" id="panel-new-season-6"><p>season six</p></section>'''
        pages = make_site.split_site_pages(fixture)
        self.assertEqual(set(pages), {'index.html', 'new-season-6.html'})
        for page in pages.values():
            self.assertIn('https://gyogun-season6-seating.doppel-tag.workers.dev/', page)
            self.assertIn('https://gyogun-five-seating.doppel-tag.workers.dev/', page)
            self.assertIn('href="table-manager.html"', page)
            self.assertLess(page.index('>シーズン6 卓組管理<'), page.index('>シーズン5 卓組管理<'))
            self.assertIn('class="ops-menu-links"', page)
            self.assertIn('position:static', page)


if __name__ == '__main__':
    unittest.main()
