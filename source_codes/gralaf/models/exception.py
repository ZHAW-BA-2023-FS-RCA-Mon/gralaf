class NewMetricFound(Exception):

    def __init__(self, metric_name):
        self.metric_name = metric_name
        self.message = f"New metric '{self.metric_name}' is discovered."
        super().__init__(self.message)

    def __str__(self):
        return self.message
