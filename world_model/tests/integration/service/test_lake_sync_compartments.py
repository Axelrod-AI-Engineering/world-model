"""The lake sync on the unified model's compartments (api/lake_sync.py): a document added to a compartment login's lake tenant
is read against that compartment's view and imported into the main engine through the view's narrowing, so what a client
adds reaches only the companies of its compartment, and the other organizations' tenants are not touched."""

from __future__ import annotations

import asyncio

import pytest

from axelrod_ingest.contract.world_view import WorldView
from tests.integration.service.test_compartment_logins import ENV, MAIN, NW, NW_OWN, WN
from tests.service.helpers import Signer, data, service

pytestmark = pytest.mark.integration
SIGNER = Signer()
# after the unified demo's last day (September 1), so the model has not seen these values
CRUDE_NOTE = b"Data, September 20, 2026. The crude price rose to $108 a barrel."
ACME_NOTE = b"Data, September 22, 2026. The crude price rose to $109 a barrel."
RATE_NOTE = b"Data, September 21, 2026. The central bank held rates at 4.0%."      # outside northwind's compartment
U = "/v1/world-models/unified_demo"


def test_a_compartments_tenant_syncs_into_the_unified_model_through_its_narrowing():
    with service(SIGNER, scenario="unified_demo", review=None, **ENV) as c:
        app = c.app
        sync = app.state.lake_sync
        sync.enabled = True
        # the console adds a crude-oil note and a rates note for northwind (a compartment), and a note of its own for acme
        for tenant, note, name in (("nw", CRUDE_NOTE, "crude.txt"), ("nw", RATE_NOTE, "rates.txt"),
                                   ("acme", ACME_NOTE, "acme.txt")):
            app.state.ingestor.ingest_file(tenant, note, name, WorldView(), source="Synthetic wire",
                                           source_type="central_bank")
        asyncio.run(sync.tick())
        ctl = app.state.axelrod.controller
        nw = data(c.get(f"{WN}/sync", headers=NW))
        assert (nw["seen"], nw["read"], nw["failures"], nw["last_error"]) == (2, 2, 0, None)
        assert nw["imported"] == 1                               # the central bank's rate is outside the compartment
        mine = [p for p in ctl.proposals.values() if p.event.ops]
        assert mine, "the northwind document reached the one engine"
        ops = [op for p in mine for op in p.event.ops]
        targets = {getattr(getattr(op, "target", None), "subentity_id", None) for op in ops} - {None}
        assert targets and all(t.split(".")[0] in NW_OWN for t in targets), targets
        # the whole model's own tenant had nothing to read; the compartment's ledger names the document
        assert data(c.get(f"{U}/sync", headers=MAIN))["seen"] == 0
        docs = {d.filename: d for d in app.state.lake.list_documents("nw", limit=5)}
        doc = docs["crude.txt"]
        rec = app.state.lake.get_idempotency("nw", "northwind_focus", "lake-sync", doc.id)
        assert rec is not None and rec.fingerprint == "imported"
        quiet = app.state.lake.get_idempotency("nw", "northwind_focus", "lake-sync", docs["rates.txt"].id)
        assert quiet is not None and quiet.fingerprint == "no_signals"     # the central bank is not in the compartment
        assert app.state.lake.get_idempotency("nw", "unified_demo", "lake-sync", doc.id) is None
        assert [r.by for r in app.state.lake.list_imports("nw")] == ["lake-sync"]
        # acme's tenant is its own: its document is in acme's ledger only, and northwind's ledger names northwind's
        (adoc,) = app.state.lake.list_documents("acme", limit=5)
        assert app.state.lake.get_idempotency("acme", "acme_unified_focus", "lake-sync", adoc.id) is not None
        assert app.state.lake.get_idempotency("acme", "northwind_focus", "lake-sync", adoc.id) is None
        assert app.state.lake.get_idempotency("nw", "acme_unified_focus", "lake-sync", doc.id) is None
        # nothing is read twice
        before = len(ctl.proposals)
        asyncio.run(sync.tick())
        assert len(ctl.proposals) == before and data(c.get(f"{WN}/sync", headers=NW))["read"] == 2
