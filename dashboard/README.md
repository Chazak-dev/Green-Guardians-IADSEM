Green Guardians Dashboard (Person 4)

Exact GitHub placement

Create this folder at the root of the repository:

dashboard/

Then upload:

dashboard/app.py

You do not need to modify, replace, or delete any existing Python/config file.

Install the dashboard dependency

From the repository root:

pip install streamlit

The existing project already uses PyYAML, so app.py can read the existing configuration file without changing requirements.txt.

Run it

From the repository root:

streamlit run dashboard/app.py

The dashboard reads the current project's existing outputs:

config/Green_Guardians_settings.yaml
results/mission_log.jsonl
results/images/

Important architecture note

The current project configuration defines communication as in-process Python calls/queues. The existing MissionController.get_dashboard_status() returns a live DashboardStatusOutput, but that object exists only inside the python main.py process.

Because this dashboard is intentionally added without changing any existing code, it does not try to fake a live API or modify main.py. Instead, it visualizes the persisted mission log and evidence images that the current project already writes.
