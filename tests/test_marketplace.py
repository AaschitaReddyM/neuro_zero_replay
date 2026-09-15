"""Tests for ArtifactMarketplace cataloging and search."""
from src.artifact.marketplace import ArtifactMarketplace


def test_marketplace_loads_artifacts():
    """Verify that ArtifactMarketplace correctly scans and indexes available artifacts."""
    marketplace = ArtifactMarketplace()
    artifacts = marketplace.list_artifacts()
    assert len(artifacts) >= 1
    
    # Verify lookup_member_balance is indexed
    lookup = marketplace.get_artifact("lookup_member_balance")
    assert lookup is not None
    assert lookup.metadata.capability_name == "lookup_member_balance"
    assert "member_id" in lookup.parameters


def test_marketplace_search():
    """Verify artifact search filtering."""
    marketplace = ArtifactMarketplace()
    results = marketplace.search_artifacts("member")
    assert any(a["capability_name"] == "lookup_member_balance" for a in results)
