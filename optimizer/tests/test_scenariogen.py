import os
import sys
import yaml
import pytest

# Add the project root to sys.path so we can import from tools.scenariogen
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from tools.scenariogen.run import generate_forecast, generate_telemetry

SCENARIOS_DIR = os.path.join(PROJECT_ROOT, 'tools', 'scenariogen', 'scenarios')

def get_scenarios():
    scenarios = []
    if os.path.exists(SCENARIOS_DIR):
        for f in os.listdir(SCENARIOS_DIR):
            if f.endswith('.yml'):
                with open(os.path.join(SCENARIOS_DIR, f), 'r') as yml:
                    scenarios.append(yaml.safe_load(yml))
    return scenarios

@pytest.mark.parametrize("scenario", get_scenarios())
def test_all_scenarios_validate(scenario):
    forecast = generate_forecast(scenario)
    assert forecast['site_id'] == 'site-scenario'
    
    telemetry = generate_telemetry(scenario)
    assert telemetry['site_id'] == 'site-scenario'
