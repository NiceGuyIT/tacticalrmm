import pytz
from django.utils import timezone as djangotime
from django.conf import settings
from packaging import version as pyver

from autotasks.models import AutomatedTask
from autotasks.tasks import delete_win_task_schedule
from checks.tasks import prune_check_history
from agents.tasks import clear_faults_task, prune_agent_history
from alerts.tasks import prune_resolved_alerts
from core.models import CoreSettings
from logs.tasks import prune_debug_log, prune_audit_log
from tacticalrmm.celery import app
from tacticalrmm.utils import AGENT_DEFER
from agents.models import Agent
from clients.models import Client, Site
from alerts.models import Alert


@app.task
def core_maintenance_tasks():
    # cleanup expired runonce tasks
    tasks = AutomatedTask.objects.filter(
        task_type="runonce",
        remove_if_not_scheduled=True,
    ).exclude(last_run=None)

    for task in tasks:
        agent_tz = pytz.timezone(task.agent.timezone)
        task_time_utc = task.run_time_date.replace(tzinfo=agent_tz).astimezone(pytz.utc)
        now = djangotime.now()

        if now > task_time_utc:
            delete_win_task_schedule.delay(task.pk)

    core = CoreSettings.objects.first()

    # remove old CheckHistory data
    if core.check_history_prune_days > 0:  # type: ignore
        prune_check_history.delay(core.check_history_prune_days)  # type: ignore

    # remove old resolved alerts
    if core.resolved_alerts_prune_days > 0:  # type: ignore
        prune_resolved_alerts.delay(core.resolved_alerts_prune_days)  # type: ignore

    # remove old agent history
    if core.agent_history_prune_days > 0:  # type: ignore
        prune_agent_history.delay(core.agent_history_prune_days)  # type: ignore

    # remove old debug logs
    if core.debug_log_prune_days > 0:  # type: ignore
        prune_debug_log.delay(core.debug_log_prune_days)  # type: ignore

    # remove old audit logs
    if core.audit_log_prune_days > 0:  # type: ignore
        prune_audit_log.delay(core.audit_log_prune_days)  # type: ignore

    # clear faults
    if core.clear_faults_days > 0:  # type: ignore
        clear_faults_task.delay(core.clear_faults_days)  # type: ignore


def _get_failing_data(agents):
    data = {"error": False, "warning": False}
    for agent in agents:
        if agent.maintenance_mode:
            break

        if agent.overdue_email_alert or agent.overdue_text_alert:
            if agent.status == "overdue":
                data["error"] = True
                break

        if agent.checks["has_failing_checks"]:

            if agent.checks["warning"]:
                data["warning"] = True

            if agent.checks["failing"]:
                data["error"] = True
                break

        if agent.autotasks.exists():  # type: ignore
            for i in agent.autotasks.all():  # type: ignore
                if i.status == "failing" and i.alert_severity == "error":
                    data["error"] = True
                    break

    return data


@app.task
def cache_db_fields_task():
    # update client/site failing check fields and agent counts
    for site in Site.objects.all():
        agents = site.agents.defer(*AGENT_DEFER)
        site.failing_checks = _get_failing_data(agents)
        site.agent_count = agents.count()
        site.save(update_fields=["failing_checks", "agent_count"])

    for client in Client.objects.all():
        agents = Agent.objects.defer(*AGENT_DEFER).filter(site__client=client)
        client.failing_checks = _get_failing_data(agents)
        client.agent_count = agents.count()
        client.save(update_fields=["failing_checks", "agent_count"])

    for agent in Agent.objects.defer(*AGENT_DEFER):
        if (
            pyver.parse(agent.version) >= pyver.parse("1.6.0")
            and agent.status == "online"
        ):
            # change agent update pending status to completed if agent has just updated
            if (
                pyver.parse(agent.version) == pyver.parse(settings.LATEST_AGENT_VER)
                and agent.pendingactions.filter(
                    action_type="agentupdate", status="pending"
                ).exists()
            ):
                agent.pendingactions.filter(
                    action_type="agentupdate", status="pending"
                ).update(status="completed")

            # sync scheduled tasks
            if agent.autotasks.exclude(sync_status="synced").exists():  # type: ignore
                tasks = agent.autotasks.exclude(sync_status="synced")  # type: ignore

                for task in tasks:
                    try:
                        if task.sync_status == "pendingdeletion":
                            task.delete_task_on_agent()
                        elif task.sync_status == "initial":
                            task.modify_task_on_agent()
                        elif task.sync_status == "notsynced":
                            task.create_task_on_agent()
                    except:
                        continue

            # handles any alerting actions
            if Alert.objects.filter(agent=agent, resolved=False).exists():
                try:
                    Alert.handle_alert_resolve(agent)
                except:
                    continue

        # update pending patches and pending action counts
        agent.pending_actions_count = agent.pendingactions.filter(
            status="pending"
        ).count()
        agent.has_patches_pending = (
            agent.winupdates.filter(action="approve").filter(installed=False).exists()
        )
        agent.save(update_fields=["pending_actions_count", "has_patches_pending"])
