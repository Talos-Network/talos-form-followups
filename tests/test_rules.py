"""Unit tests for the rules engine. Synthetic records only — the real
fixture.json is gitignored and must never be needed for tests to pass.
Cases mirror the real situations found in the 25 Aug 2026 fixture.
Run: python3 -m unittest discover -s tests -t .
"""

import unittest
from datetime import date

from rules import (FELLOW, SUPERVISOR, DueNudge, PriorNudge, add_months,
                   latest_request_date, who_needs_nudging)

TODAY = date(2026, 8, 25)


def placement(pid="rec1", name="Test Fellow", start="2026-06-01", end="2027-05-31",
              expected=2, actual_f=0, actual_s=0, paused=False, completed=False,
              fellow_dates=(), supervisor_dates=(), no_start=False,
              supervisor_email="sup@example.org"):
    fields = {
        "Name": name, "First Name": name.split()[0],
        "Fellow Email": "fellow@example.org", "Placement Org": "Example Org",
        "Expected Reports": expected,
        "Actual Reports (Fellows)": actual_f, "Actual Reports (Supervisors)": actual_s,
        "Placement Paused?": paused, "Placement Completed": completed,
        "Fellow Form Link": "https://forms/f", "Supervisor Form Link": "https://forms/s",
        "Email (from Supervisor)": [supervisor_email] if supervisor_email else [],
        "Supervisor First Name": ["Sam"] if supervisor_email else [],
    }
    if not no_start:
        fields["Start Date"] = start
        fields["End Date"] = end
    return {"id": pid, "fields": fields,
            "fellow_form_dates": list(fellow_dates),
            "supervisor_form_dates": list(supervisor_dates)}


def due_for(result, recipient):
    return [n for n in result.due if n.recipient == recipient]


class TestDateMaths(unittest.TestCase):
    def test_add_months_clamps_short_months(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(add_months(date(2024, 1, 31), 1), date(2024, 2, 29))
        self.assertEqual(add_months(date(2026, 1, 31), 2), date(2026, 3, 31))

    def test_latest_request_none_before_first_anniversary(self):
        self.assertIsNone(latest_request_date(date(2026, 8, 1), date(2026, 8, 25)))

    def test_latest_request_finds_most_recent_anniversary(self):
        self.assertEqual(latest_request_date(date(2026, 4, 20), TODAY), date(2026, 8, 20))
        self.assertEqual(latest_request_date(date(2026, 6, 1), TODAY), date(2026, 8, 1))


class TestSilencers(unittest.TestCase):
    def test_paused_never_chased_either_role(self):
        r = who_needs_nudging([placement(paused=True, expected=5)], [], TODAY)
        self.assertEqual(r.due, [])
        self.assertEqual(len(r.silenced), 1)

    def test_completed_never_chased(self):
        r = who_needs_nudging([placement(completed=True, expected=5)], [], TODAY)
        self.assertEqual(r.due, [])

    def test_no_start_date_is_unprocessable_not_silent(self):
        r = who_needs_nudging([placement(no_start=True)], [], TODAY)
        self.assertEqual(r.due, [])
        self.assertEqual(len(r.unprocessable), 1)
        self.assertIn("no Start Date", r.unprocessable[0])

    def test_brand_new_nothing_due(self):
        r = who_needs_nudging([placement(start="2026-08-10", expected=0)], [], TODAY)
        self.assertEqual(r.due, [])
        self.assertTrue(any("first form not yet due" in q for q in r.quiet))


class TestLadder(unittest.TestCase):
    def test_rung1_after_seven_days(self):
        # start 1 Jun -> request 1 Aug -> 24 days late, no history: rung 1 (climb one at a time)
        r = who_needs_nudging([placement()], [], TODAY)
        fellow = due_for(r, FELLOW)
        self.assertEqual(len(fellow), 1)
        self.assertEqual(fellow[0].rung, 1)

    def test_nothing_due_within_seven_days(self):
        # start 20 Apr -> request 20 Aug -> only 5 days: quiet
        p = placement(start="2026-04-20", expected=3, actual_f=3, actual_s=3)
        r = who_needs_nudging([p], [], TODAY)
        self.assertEqual(r.due, [])

    def test_rung2_after_sent_rung1_and_threshold(self):
        h = [PriorNudge("rec1", FELLOW, 1, "Sent", date(2026, 8, 8))]
        r = who_needs_nudging([placement()], h, TODAY)
        self.assertEqual(due_for(r, FELLOW)[0].rung, 2)

    def test_spacing_guard_blocks_backtoback(self):
        h = [PriorNudge("rec1", FELLOW, 1, "Sent", date(2026, 8, 21))]  # 4 days ago
        r = who_needs_nudging([placement()], h, TODAY)
        self.assertEqual(due_for(r, FELLOW), [])

    def test_rejected_silences_the_month(self):
        h = [PriorNudge("rec1", FELLOW, 1, "Rejected", date(2026, 8, 8))]
        r = who_needs_nudging([placement()], h, TODAY)
        self.assertEqual(due_for(r, FELLOW), [])

    def test_pending_draft_blocks_duplicate(self):
        h = [PriorNudge("rec1", FELLOW, 1, "Pending", date(2026, 8, 8))]
        r = who_needs_nudging([placement()], h, TODAY)
        self.assertEqual(due_for(r, FELLOW), [])

    def test_cap_three_per_month(self):
        h = [PriorNudge("rec1", FELLOW, k, "Sent", date(2026, 8, 1 + 7 * k))
             for k in (1, 2, 3)]
        r = who_needs_nudging([placement()], h, date(2026, 8, 30))
        self.assertEqual(due_for(r, FELLOW), [])

    def test_last_months_history_does_not_count(self):
        h = [PriorNudge("rec1", FELLOW, 3, "Sent", date(2026, 7, 25))]
        r = who_needs_nudging([placement()], h, TODAY)
        self.assertEqual(due_for(r, FELLOW)[0].rung, 1)


class TestPredicateAndDepth(unittest.TestCase):
    def test_catching_up_not_nudged(self):
        # Caroline: behind 1 but submitted after the Aug request
        p = placement(expected=2, actual_f=1, fellow_dates=["2026-08-10"])
        r = who_needs_nudging([p], [], TODAY)
        self.assertEqual(due_for(r, FELLOW), [])

    def test_over_delivery_not_nudged(self):
        # Cesar: actual > expected, two submissions in the current month
        p = placement(start="2026-04-20", expected=3, actual_f=4,
                      fellow_dates=["2026-05-20", "2026-06-21", "2026-08-17", "2026-08-24"],
                      actual_s=3, supervisor_dates=["2026-06-02", "2026-06-30", "2026-07-22"])
        r = who_needs_nudging([p], [], TODAY)
        self.assertEqual(due_for(r, FELLOW), [])

    def test_depth_is_one_when_only_current_cycle_missed(self):
        # submitted mid-July, so only the 10 Aug request is unanswered —
        # depth 1 even inside the base's Expected-Reports grace window
        p = placement(start="2026-01-10", fellow_dates=["2026-07-15"])
        r = who_needs_nudging([p], [], date(2026, 8, 18))  # request 10 Aug, +8 days
        fellow = due_for(r, FELLOW)
        self.assertEqual(len(fellow), 1)
        self.assertEqual(fellow[0].depth, 1)
        self.assertEqual(fellow[0].last_submission, date(2026, 7, 15))

    def test_late_submission_just_before_request_covers_it(self):
        # the Marietta case: submitted 2 days before the next request went
        # out — that request is treated as already covered, no chase
        p = placement(start="2026-06-01", fellow_dates=["2026-07-30"])  # request 1 Aug
        r = who_needs_nudging([p], [], TODAY)
        self.assertEqual(due_for(r, FELLOW), [])

    def test_submission_outside_grace_window_does_not_cover(self):
        # 12 days before the request: outside the 10-day grace, still chased
        p = placement(start="2026-06-01", fellow_dates=["2026-07-20"])  # request 1 Aug
        r = who_needs_nudging([p], [], TODAY)
        self.assertEqual(len(due_for(r, FELLOW)), 1)
        self.assertEqual(due_for(r, FELLOW)[0].depth, 1)

    def test_covering_form_wipes_the_slate(self):
        # never submitted until July despite starting in January; that one
        # covering form resets depth — only cycles after it count
        p = placement(start="2026-01-01", fellow_dates=["2026-07-10"])
        r = who_needs_nudging([p], [], TODAY)
        self.assertEqual(due_for(r, FELLOW)[0].depth, 1)  # only 1 Aug missed

    def test_supervisor_cc_at_depth_three(self):
        # last report mid-May: June, July, August requests all unanswered
        p = placement(start="2026-01-01", fellow_dates=["2026-05-15"])
        r = who_needs_nudging([p], [], TODAY)
        nudge = due_for(r, FELLOW)[0]
        self.assertEqual(nudge.depth, 3)
        self.assertTrue(nudge.cc_supervisor)
        self.assertEqual(nudge.supervisor_email, "sup@example.org")

    def test_no_cc_below_depth_three(self):
        p = placement(start="2026-01-01", fellow_dates=["2026-06-15"])
        r = who_needs_nudging([p], [], TODAY)
        nudge = due_for(r, FELLOW)[0]
        self.assertEqual(nudge.depth, 2)
        self.assertFalse(nudge.cc_supervisor)

    def test_no_cc_without_supervisor_email(self):
        p = placement(start="2026-01-01", fellow_dates=["2026-05-15"], supervisor_email="")
        r = who_needs_nudging([p], [], TODAY)
        self.assertFalse(due_for(r, FELLOW)[0].cc_supervisor)


class TestSupervisors(unittest.TestCase):
    def test_supervisor_chased_independently_of_fellow(self):
        # fellow submitted, supervisor did not
        p = placement(expected=2, actual_f=2, fellow_dates=["2026-08-10", "2026-07-05"],
                      actual_s=0)
        r = who_needs_nudging([p], [], TODAY)
        self.assertEqual(due_for(r, FELLOW), [])
        sup = due_for(r, SUPERVISOR)
        self.assertEqual(len(sup), 1)
        self.assertEqual(sup[0].rung, 1)
        self.assertEqual(sup[0].email, "sup@example.org")

    def test_supervisor_of_many_fellows_chased_per_placement(self):
        p1 = placement(pid="rec1", name="Fellow One", expected=2, actual_s=0)
        p2 = placement(pid="rec2", name="Fellow Two", start="2026-04-20",
                       expected=3, actual_s=3,
                       supervisor_dates=["2026-06-02", "2026-06-30", "2026-08-21"])
        r = who_needs_nudging([p1, p2], [], TODAY)
        sup = due_for(r, SUPERVISOR)
        self.assertEqual(len(sup), 1)  # chased for rec1 only; rec2 current month done
        self.assertEqual(sup[0].placement_id, "rec1")

    def test_missing_supervisor_email_is_unprocessable(self):
        p = placement(expected=2, actual_s=0, supervisor_email="")
        r = who_needs_nudging([p], [], TODAY)
        self.assertTrue(any("no supervisor email" in u for u in r.unprocessable))


class TestConsolidation(unittest.TestCase):
    def test_one_email_per_supervisor(self):
        from rules import consolidate_supervisor_nudges
        p1 = placement(pid="rec1", name="Fellow One", expected=2, actual_s=0)
        p2 = placement(pid="rec2", name="Fellow Two", expected=2, actual_s=0)
        p3 = placement(pid="rec3", name="Fellow Three", expected=2, actual_s=0,
                       supervisor_email="other@example.org")
        r = who_needs_nudging([p1, p2, p3], [], TODAY)
        fellows, batches = consolidate_supervisor_nudges(r.due, r.supervisor_context)
        self.assertEqual(len(batches), 2)  # sup@ (two fellows) and other@
        big = next(b for b in batches if b.email == "sup@example.org")
        self.assertEqual({n.person_name for n in big.items}, {"Fellow One", "Fellow Two"})
        self.assertEqual(big.rung, 1)

    def test_context_attaches_but_never_creates_a_batch(self):
        from rules import consolidate_supervisor_nudges
        # Same supervisor: one placement 24 days late (due), one requested
        # 5 days ago (outstanding, below rung 1) -> one email, both mentioned.
        p_due = placement(pid="rec1", name="Fellow One", expected=2, actual_s=0)
        p_ctx = placement(pid="rec2", name="Fellow Two", start="2026-04-20",
                          expected=3, actual_s=2,
                          supervisor_dates=["2026-06-02", "2026-06-30"])
        r = who_needs_nudging([p_due, p_ctx], [], TODAY)
        fellows, batches = consolidate_supervisor_nudges(r.due, r.supervisor_context)
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0].items), 1)
        self.assertEqual(batches[0].also_outstanding[0].person_name, "Fellow Two")
        # Alone (without the due placement), context creates no email at all.
        r2 = who_needs_nudging([p_ctx], [], TODAY)
        fellows2, batches2 = consolidate_supervisor_nudges(r2.due, r2.supervisor_context)
        self.assertEqual(batches2, [])


if __name__ == "__main__":
    unittest.main()
