from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from evidence_bridge import bridge_observations
from evidence_contract import EvidenceCapability
from parsers.asm_mapping import map_asm_record


def test_asm_ip_asn_subject_stays_asn_while_candidate_domain_is_preserved():
    observations = map_asm_record(
        {
            "domain": "sony.com",
            "ip.asn": 64500,
            "ip.asn.org": "Sony Corporation",
        },
        expected_entity_name="Sony Corporation",
    )
    ip_asn = next(o for o in observations if o.capability is EvidenceCapability.IP_ASN_OWNERSHIP)
    assert ip_asn.subject == "AS64500"
    assert ip_asn.raw["candidate_domain"] == "sony.com"

    bridged = bridge_observations(
        [ip_asn],
        entity_lei="529900R5WX9N2OI2N910",
        entity_name="Sony Corporation",
    )
    assert bridged[0]["domain"] == "sony.com"
    assert bridged[0]["raw"]["candidate_domain"] == "sony.com"
