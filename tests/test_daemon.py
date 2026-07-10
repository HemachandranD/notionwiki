from pathlib import Path

from notion_wiki.config import Config
from notion_wiki.daemon import run_forever, tick_once
from tests.fakes import FakeNotionClient, make_raw_page, paragraph_block


def test_tick_once_runs_a_pull_cycle(tmp_path: Path, monkeypatch):
    wiki_root = tmp_path / "wiki"
    state_dir = tmp_path / "state"
    config = Config(wiki_root=wiki_root)

    fake_client = FakeNotionClient(
        pages=[make_raw_page("p1", "Bridge Design", last_edited_time="2026-07-09T14:00:00.000Z")],
        blocks={"p1": [paragraph_block("hello")]},
    )
    monkeypatch.setattr("notion_wiki.daemon.NotionClient", lambda token: fake_client)

    tick_once(config, "fake-token", state_dir)

    dest = wiki_root / "raw" / "notion" / "bridge-design.md"
    assert dest.exists()


class RecordingScheduler:
    instances: list["RecordingScheduler"] = []

    def __init__(self, *a, **k):
        self.jobs = []
        self.started = False
        RecordingScheduler.instances.append(self)

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append((func, trigger, kwargs))

    def start(self):
        self.started = True
        # Run the job once synchronously so tests can assert side effects
        # without actually blocking on a real scheduler loop.
        for func, _trigger, _kwargs in self.jobs:
            func()


def test_run_forever_schedules_interval_job_and_runs_it(tmp_path: Path, monkeypatch):
    wiki_root = tmp_path / "wiki"
    state_dir = tmp_path / "state"
    config = Config(wiki_root=wiki_root)

    fake_client = FakeNotionClient(
        pages=[make_raw_page("p1", "Bridge Design", last_edited_time="2026-07-09T14:00:00.000Z")],
        blocks={"p1": [paragraph_block("hello")]},
    )
    monkeypatch.setattr("notion_wiki.daemon.NotionClient", lambda token: fake_client)
    monkeypatch.setattr("apscheduler.schedulers.blocking.BlockingScheduler", RecordingScheduler)

    RecordingScheduler.instances.clear()
    run_forever(config, "fake-token", state_dir, interval_seconds=5)

    assert len(RecordingScheduler.instances) == 1
    scheduler = RecordingScheduler.instances[0]
    assert scheduler.started is True
    assert scheduler.jobs[0][1] == "interval"
    assert scheduler.jobs[0][2]["seconds"] == 5
    assert (wiki_root / "raw" / "notion" / "bridge-design.md").exists()


def test_run_forever_serves_graph_in_background_thread(tmp_path: Path, monkeypatch):
    wiki_root = tmp_path / "wiki"
    state_dir = tmp_path / "state"
    config = Config(wiki_root=wiki_root)

    fake_client = FakeNotionClient(pages=[])
    monkeypatch.setattr("notion_wiki.daemon.NotionClient", lambda token: fake_client)
    monkeypatch.setattr("apscheduler.schedulers.blocking.BlockingScheduler", RecordingScheduler)

    serve_calls = []
    monkeypatch.setattr(
        "notion_wiki.graph.server.serve", lambda root, port=7777: serve_calls.append((root, port))
    )

    RecordingScheduler.instances.clear()
    run_forever(
        config, "fake-token", state_dir, interval_seconds=30, serve_graph=True, graph_port=8888
    )

    import time

    time.sleep(0.05)  # let the daemon thread run
    assert serve_calls == [(wiki_root, 8888)]
