import unittest
from datetime import datetime, timezone
from audit_seating import reconcile


class AuditTests(unittest.TestCase):
    def test_matching_and_collisions(self):
        data = {'updated': datetime.fromtimestamp(20000, timezone.utc).isoformat(),
                'records': [{'uuid': 'x', 'players': [1, 2, 3], 'end': 19000}]}
        draft = {'id': 'a', 'players': [3, 2, 1], 'end': 19060}
        self.assertEqual(reconcile(data, [draft])[0]['status'], 'matched')
        self.assertTrue(all(x['status'] == 'review' for x in reconcile(data, [draft, {**draft, 'id': 'b'}])))
        self.assertEqual(reconcile(data, [{**draft, 'end': 10000}])[0]['status'], 'review')
        self.assertEqual(reconcile(data, [{**draft, 'end': 21000}])[0]['status'], 'pending')
        self.assertEqual(reconcile(data, [{**draft, 'cancelled': True}])[0]['status'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
