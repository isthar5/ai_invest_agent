import lightgbm as lgb
import shap

class QuantModel:
    def __init__(self):
        self.model = lgb.LGBMRegressor(
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6
        )
        self.explainer = None

    def train(self, X, y):
        self.model.fit(X, y)
        self.explainer = shap.TreeExplainer(self.model)

    def predict(self, X):
        preds = self.model.predict(X)
        shap_values = self.explainer.shap_values(X)
        return preds, shap_values