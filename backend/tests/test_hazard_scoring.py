import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from django.test import SimpleTestCase

from apps.history.hazard_data import STUDY_END, STUDY_START, build_dataset
from apps.history.hazard_models import export_logistic, make_logistic
from apps.history.hazard_scoring import FitError, score_logistic, score_two_part
from apps.history.two_part import TwoPartFit, WhenFit
from tests.hazard_fixtures import toy_inputs


class ScoringTests(SimpleTestCase):
    def test_numpy_scoring_matches_the_pipeline(self):
        terrain, rain, pos = toy_inputs(n_barangays=4)
        ds, _ = build_dataset('Flood', terrain, rain, pos, STUDY_START, STUDY_END)
        X = ds.X.copy()
        X[::50, 6] = np.nan                      # imputation is exercised
        pipe = make_logistic().fit(X, ds.y)
        fit = export_logistic(pipe, ds.features, X)
        self.assertEqual(fit['kind'], 'logistic_regression')
        self.assertEqual(fit['log_columns'], [0, 1, 2, 3, 4])
        self.assertEqual(set(fit['training_max']), set(ds.features))
        json.dumps(fit, allow_nan=False)         # strict JSON
        np.testing.assert_allclose(score_logistic(fit, X), pipe.predict_proba(X)[:, 1], atol=1e-9, rtol=0)
        back = json.loads(json.dumps(fit))
        np.testing.assert_allclose(score_logistic(back, X), pipe.predict_proba(X)[:, 1], atol=1e-9, rtol=0)

    def _two_part(self):
        when = WhenFit(('log1p_r3', 'storm72'), np.array([0.5, 1.0]), {'geoalert': -3.0})
        return TwoPartFit('Flood', when, {1: 0.2, 2: 0.9}, 0.05, None, {}).to_json()

    def test_two_part_scoring_is_q_times_share(self):
        fit = self._two_part()
        when_X = np.array([[2.0, 0.0], [4.0, 1.0]])
        q = 1 / (1 + np.exp(-(-3.0 + when_X @ np.array([0.5, 1.0]))))
        day_index = np.array([0, 1, 1, 0])
        ids = np.array([1, 1, 2, 2])
        got = score_two_part(fit, when_X, day_index, ids)
        np.testing.assert_allclose(got, [q[0] * 0.2, q[1] * 0.2, q[1] * 0.9, q[0] * 0.9], atol=1e-12)

    def test_a_barangay_without_a_share_is_an_error(self):
        with self.assertRaises(FitError):
            score_two_part(self._two_part(), np.array([[2.0, 0.0]]), np.array([0]), np.array([99]))

    def test_scoring_imports_no_sklearn(self):
        backend = Path(__file__).resolve().parent.parent
        code = ("import django; django.setup(); import sys; import apps.history.hazard_scoring; "
                "print('sklearn' in sys.modules, 'xgboost' in sys.modules)")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [str(backend), os.environ.get('PYTHONPATH', '')])))
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env, cwd=backend)
        self.assertEqual(out.stdout.strip(), 'False False', out.stderr)

    def test_xgboost_is_not_required(self):
        text = (Path(__file__).resolve().parent.parent / 'requirements' / 'base.txt').read_text(encoding='utf-8')
        self.assertNotIn('xgboost', text.lower())
