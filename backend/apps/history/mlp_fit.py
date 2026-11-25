"""
One seed of the landslide neural network (ruling R59). This module imports only
numpy and scikit-learn, so a joblib worker process can load it without Django;
landslide_training fits the seeds side by side when MLP_JOBS > 1. Every seed
keeps its own random_state, so the fitted networks are the ones a one-by-one
fit gives.
"""
import warnings

from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def fit_one(X, y, w, random_state: int):
    """The scaled (32, 16) ReLU network, Adam, L2 1e-3, 500 epochs, fitted with sample weights."""
    m = make_pipeline(StandardScaler(), MLPClassifier(
        hidden_layer_sizes=(32, 16), activation='relu', solver='adam', alpha=1e-3, max_iter=500,
        early_stopping=False, random_state=random_state))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', ConvergenceWarning)
        m.fit(X, y, mlpclassifier__sample_weight=w)
    return m
