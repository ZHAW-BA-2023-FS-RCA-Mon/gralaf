import logging
import random

from flask import Flask, request, render_template

LOG_LEVEL = "INFO"
TIME_FORMAT = '%H:%M:%S'
LOGGING_FORMAT = "%(asctime)s.%(msecs)03d-> %(message)s"

app = Flask(__name__, static_url_path='/static', static_folder='static')
logger = logging.getLogger(__name__)

trails_file = "tosca_single_instance.yaml"
reported_incidents = []
metrics = []
liability_reports = []
service_providers = {
    "edgex-core-data": "SP1",
    "edgex-core-metadata": "SP1",
    "edgex-core-command": "SP1",
    "edgex-device-mqtt": "SP3",
    "edgex-device-virtual": "SP3",
    "edgex-device-rest": "SP3",
    "edgex-support-notifications": "SP4",
    "edgex-support-scheduler": "SP4",
    "edgex-ui": "SP4",
    "edgex-exporter-fledge": "SP2",
    "edgex-redis": "SP2",
    "edgex-core-consul": "SP2"
}


@app.get("/trails")
def get_lasm():
    return app.send_static_file(trails_file)


@app.get("/")
def home():
    if reported_incidents:
        return render_template('incident.html', incidents=reported_incidents)
    else:
        return render_template('no_incident.html', incidents={})


@app.get("/liability")
def get_liability_reports():
    if liability_reports:
        return render_template('report.html', reports=liability_reports)
    else:
        return render_template('no_report.html', reports={})


@app.get("/metrics")
def get_metrics():
    if metrics:
        return render_template('report_with_metrics.html', reports=metrics)
    else:
        return render_template('no_report.html', reports={})


@app.post("/incident")
def post_incident():
    request_json = request.get_json()
    request_json.update({"responsible_provider": "SP1", "penalty": "$250"})
    reported_incidents.append(request_json)
    return "<p>Here is your report</p>"


@app.post("/maleaf/serviceData/")
def post_metrics():
    request_json = request.get_json()
    metric_texts = [""]
    for metric_name, metric_value in request_json.items():
        metric_name = metric_name.replace("_edgex", "")
        if isinstance(metric_value, float):
            metric_text = '%s=%.2f' % (metric_name, metric_value)
        else:
            metric_text = '%s=%s' % (metric_name, metric_value)
        metric_texts.append(metric_text)
    metric_texts.sort()
    request_json["metrics_ordered"] = '<br>'.join(metric_texts)
    metrics.append(request_json)
    return "<p>Here is your report</p>"


@app.post("/maleaf/incidentReport/")
def post_incident_with_probabilities():
    request_json = request.get_json()
    for index, result in enumerate(request_json["results"].copy()):
        request_json["results"][index]["responsible_provider"] = service_providers[
            result["service_name"].replace('_', '-')]
        request_json["results"][index]["penalty"] = f"${random.randint(1, 9) * 100}"
        request_json["results"][index]["probability"] = f"{result['probability'] * 100:.2f}%"
    request_json["metrics"] = '<br>'.join(
        ['%s:: %s' % (key, value) for (key, value) in request_json["metrics"].items()])
    liability_reports.append(request_json)
    return "<p>Here is your report</p>"


@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')


@app.get("/rca_report")
def get_rca_report():
    # return app.send_static_file('template_for_rca_demo_paper.html')
    return render_template('template_for_rca_demo_paper_presentation_cbn.html')


@app.get("/sla_report")
def get_sla_report():
    return render_template('template_for_rca_demo_paper_presentation_sla.html')


if __name__ == '__main__':
    logging.basicConfig(level=getattr(logging, LOG_LEVEL),
                        format=LOGGING_FORMAT, datefmt=TIME_FORMAT)
    app.run(host='0.0.0.0', port=5001)
