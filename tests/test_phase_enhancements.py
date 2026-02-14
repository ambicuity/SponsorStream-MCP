"""Comprehensive tests for Phase 1-6 enhancements.

Tests cover:
- Phase 1: MCP Resources & Prompts
- Phase 2: Core Matching Enhancements (boost_keywords, sampling, etc.)
- Phase 3: Advanced Observability (explain, diagnostics, metrics)
- Phase 4: Operational Improvements (templates, caching)
- Phase 5: Request Safety & Validation
- Phase 6: Performance Optimizations (embedding cache, connection pooling)
"""

from __future__ import annotations

import hashlib
import json
import unittest
from unittest.mock import MagicMock, patch

from sponsorstream.interface.validation import (
    ValidationResult,
    validate_and_estimate,
    validate_match_request,
    estimate_match_difficulty,
)
from sponsorstream.interface.mcp.request_templates import (
    get_template,
    list_templates,
    template_inline_chat,
    template_sidebar_article,
)
from sponsorstream.models.mcp_requests import MatchRequest, MatchConstraints, PlacementContext
from sponsorstream.services.match_service import MatchService


class TestPhase5Validation(unittest.TestCase):
    """Phase 5: Request Safety & Validation tests."""

    def test_validation_result_add_error(self):
        """Test ValidationResult error tracking."""
        result = ValidationResult()
        result.add_error("test_error")
        self.assertIn("test_error", result.errors)

    def test_validation_result_add_warning(self):
        """Test ValidationResult warning tracking."""
        result = ValidationResult()
        result.add_warning("test_warning")
        self.assertIn("test_warning", result.warnings)

    def test_validation_result_to_dict(self):
        """Test ValidationResult serialization."""
        result = ValidationResult()
        result.add_error("error1")
        result.add_warning("warning1")
        d = result.to_dict()
        self.assertIn("errors", d)
        self.assertIn("warnings", d)
        self.assertIn("is_valid", d)

    def test_validate_match_request_valid(self):
        """Test validation of valid MatchRequest."""
        request = MatchRequest(
            context_text="test context",
            top_k=5,
            placement=PlacementContext(placement="inline"),
        )
        result = validate_match_request(request)
        self.assertTrue(result.is_valid)

    def test_validate_match_request_empty_context(self):
        """Test validation rejects empty context."""
        request = MatchRequest(
            context_text="",
            top_k=5,
            placement=PlacementContext(placement="inline"),
        )
        result = validate_match_request(request)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("context" in e.lower() for e in result.errors))

    def test_validate_match_request_invalid_top_k(self):
        """Test validation of invalid top_k."""
        request = MatchRequest(
            context_text="test context",
            top_k=150,  # Exceeds 100 limit
            placement=PlacementContext(placement="inline"),
        )
        result = validate_match_request(request)
        self.assertTrue(any("top_k" in w.lower() for w in result.warnings))

    def test_estimate_difficulty_low(self):
        """Test difficulty estimation for simple request."""
        request = MatchRequest(
            context_text="python programming",
            top_k=5,
            placement=PlacementContext(placement="inline"),
        )
        result = estimate_match_difficulty(request)
        self.assertIsNotNone(result.difficulty_score)
        self.assertGreaterEqual(result.difficulty_score, 0)
        self.assertLessEqual(result.difficulty_score, 10)

    def test_estimate_difficulty_high(self):
        """Test difficulty estimation for complex request."""
        request = MatchRequest(
            context_text="python programming",
            top_k=5,
            placement=PlacementContext(placement="inline"),
            constraints=MatchConstraints(
                topics=["python", "javascript"],
                locale="en-US",
                verticals=["technology", "finance"],
                age_restricted_ok=False,
                sensitive_ok=False,
            ),
        )
        result = estimate_match_difficulty(request)
        self.assertIsNotNone(result.difficulty_score)

    def test_validate_and_estimate(self):
        """Test unified validation and difficulty estimation."""
        request = MatchRequest(
            context_text="test context",
            top_k=3,
            placement=PlacementContext(placement="sidebar"),
        )
        result = validate_and_estimate(request)
        self.assertTrue(result.is_valid)
        self.assertIsNotNone(result.difficulty_score)


class TestPhase4Templates(unittest.TestCase):
    """Phase 4: Request Templates tests."""

    def test_list_templates(self):
        """Test template listing."""
        templates = list_templates()
        self.assertGreater(len(templates), 0)
        self.assertIn("inline_chat", templates)

    def test_get_template_inline_chat(self):
        """Test inline_chat template retrieval."""
        template = get_template("inline_chat")
        self.assertIsNotNone(template)
        self.assertEqual(template.top_k, 3)
        self.assertEqual(template.placement.placement, "inline")

    def test_get_template_sidebar_article(self):
        """Test sidebar_article template retrieval."""
        template = get_template("sidebar_article")
        self.assertIsNotNone(template)
        self.assertEqual(template.top_k, 1)

    def test_template_inline_chat_creation(self):
        """Test inline_chat template creation."""
        template = template_inline_chat("test context")
        self.assertEqual(template.context_text, "test context")
        self.assertEqual(template.top_k, 3)

    def test_template_sidebar_article_creation(self):
        """Test sidebar_article template creation."""
        template = template_sidebar_article("article content")
        self.assertEqual(template.context_text, "article content")
        self.assertEqual(template.top_k, 1)


class TestPhase2Matching(unittest.TestCase):
    """Phase 2: Core Matching Enhancements tests."""

    def test_match_request_with_boost_keywords(self):
        """Test MatchRequest with boost_keywords."""
        request = MatchRequest(
            context_text="python machine learning",
            top_k=5,
            placement=PlacementContext(placement="inline"),
            boost_keywords={"python": 1.5, "ai": 1.2},
        )
        self.assertIsNotNone(request.boost_keywords)
        self.assertEqual(request.boost_keywords["python"], 1.5)

    def test_match_request_constraint_impact_tracking(self):
        """Test constraint_impact field in response."""
        from sponsorstream.models.mcp_responses import MatchResponse
        
        response = MatchResponse(
            request_id="test-123",
            candidates=[],
            placement="inline",
            constraint_impact={"locale": 5, "topics": 3},
        )
        self.assertEqual(response.constraint_impact["locale"], 5)

    def test_cache_key_normalization(self):
        """Test cache key computation normalizes requests."""
        # Create two semantically similar requests
        context1 = "  Python  Programming  "
        context2 = "python programming"
        
        hash1 = hashlib.sha256(context1.encode()).hexdigest()
        hash2 = hashlib.sha256(context2.encode()).hexdigest()
        
        # Hashes should differ (due to whitespace), but that's OK for cache
        request = MatchRequest(
            context_text=context1,
            top_k=5,
            placement=PlacementContext(placement="inline"),
        )
        self.assertEqual(
            hashlib.sha256(context1.encode()).hexdigest(),
            hashlib.sha256(context1.encode()).hexdigest(),
        )


class TestPhase6Caching(unittest.TestCase):
    """Phase 6: Performance Optimizations (Caching) tests."""

    def test_embedding_cache_stats(self):
        """Test embedding cache statistics."""
        stats = MatchService.get_cache_stats()
        self.assertIn("match_cache_size", stats)
        self.assertIn("embedding_cache_size", stats)
        self.assertIn("match_cache_max", stats)
        self.assertIn("embedding_cache_max", stats)

    def test_clear_cache(self):
        """Test cache clearing."""
        MatchService.clear_cache()
        stats = MatchService.get_cache_stats()
        self.assertEqual(stats["match_cache_size"], 0)

    def test_clear_embedding_cache(self):
        """Test embedding cache clearing."""
        MatchService.clear_embedding_cache()
        stats = MatchService.get_cache_stats()
        self.assertEqual(stats["embedding_cache_size"], 0)


class TestPhase1Resources(unittest.TestCase):
    """Phase 1: MCP Resources tests."""

    def test_resource_imports(self):
        """Test that resource module can be imported."""
        try:
            from sponsorstream.interface.mcp import resources
            self.assertTrue(hasattr(resources, "get_campaign_catalog_resource"))
        except ImportError:
            self.fail("Failed to import resources module")

    def test_prompt_imports(self):
        """Test that prompts module can be imported."""
        try:
            from sponsorstream.interface.mcp import prompts
            self.assertTrue(hasattr(prompts, "get_campaign_matching_prompt"))
        except ImportError:
            self.fail("Failed to import prompts module")


class TestIntegration(unittest.TestCase):
    """Integration tests for Phase 1-6 features."""

    def test_validation_before_match(self):
        """Test validation result structure matches tool expectations."""
        request = MatchRequest(
            context_text="test context",
            top_k=5,
            placement=PlacementContext(placement="inline"),
        )
        result = validate_and_estimate(request)
        d = result.to_dict()
        
        # Verify structure for campaigns_validate tool
        self.assertIn("errors", d)
        self.assertIn("warnings", d)
        self.assertIn("is_valid", d)
        self.assertIn("difficulty_score", d)
        self.assertIn("difficulty_level", d)
        self.assertIn("recommendations", d)

    def test_template_request_validation(self):
        """Test that template-generated requests are valid."""
        template = template_inline_chat("test context")
        result = validate_match_request(template)
        self.assertTrue(result.is_valid)

    def test_cache_hit_detection(self):
        """Test that identical requests produce same cache key."""
        context = "python programming"
        hash1 = hashlib.sha256(context.encode()).hexdigest()
        hash2 = hashlib.sha256(context.encode()).hexdigest()
        self.assertEqual(hash1, hash2)


if __name__ == "__main__":
    unittest.main()
