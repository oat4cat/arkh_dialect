from django.test import SimpleTestCase

import numpy as np

from django.core.exceptions import FieldDoesNotExist
from . import concepts_pipeline
from .filters import LexicalEntryFilter
from .models import (
    LexicalEntry,
    LexicalForm,
    SenseSubcategory,
    SenseText,
)


class DatabaseSchemaModelTests(SimpleTestCase):
    def test_lexical_form_matches_database_table(self):
        self.assertEqual(LexicalForm._meta.db_table, "LexicalForm")
        self.assertEqual(
            LexicalForm._meta.get_field("lexical_entry").column,
            "lexical_entry_id",
        )
        self.assertEqual(LexicalForm._meta.get_field("form").column, "form")
        self.assertIs(
            LexicalForm._meta.get_field("lexical_entry").remote_field.model,
            LexicalEntry,
        )

    def test_sense_join_tables_match_database_names(self):
        self.assertEqual(SenseText._meta.db_table, "Sense_Text")
        self.assertEqual(SenseSubcategory._meta.db_table, "Sense_Subcategory")

    def test_lexical_entry_does_not_use_removed_join_tables(self):
        for field_name in ("texts", "subcategories"):
            with self.assertRaises(FieldDoesNotExist):
                LexicalEntry._meta.get_field(field_name)

    def test_filters_follow_sense_relationships(self):
        filters = LexicalEntryFilter()
        self.assertEqual(
            filters.filters["subcategories"].field_name,
            "senses__subcategories__name",
        )
        self.assertEqual(
            filters.filters["regions"].field_name,
            "senses__texts__region__name",
        )


class ClusterCandidatesTests(SimpleTestCase):
    def test_average_linkage_rejects_weak_bridge(self):
        """Average linkage не склеивает цепочку a—b—c через слабый мост b—c."""
        candidates = [
            {"lemma": lemma, "surface": lemma, "upos": "NOUN",
             "sense_id": i, "syntactic_context": lemma}
            for i, lemma in enumerate(["aa", "bb", "cc"])
        ]
        # Косинусы пар: (0,1)≈0.956 и (1,2)≈0.946 — выше порога, (0,2)≈0.809 —
        # ниже. Лексика у разных лемм нулевая, combined = 0.7·косинус.
        # Single-linkage склеил бы всех транзитивно; у average linkage среднее
        # расстояние {0,1}—{2} ≈ 0.382 > 0.35, мост не проходит.
        angles = [0.0, 17.0, 36.0]
        embeddings = np.array(
            [[np.cos(np.radians(a)), np.sin(np.radians(a))] for a in angles],
            dtype=np.float32,
        )

        labels = concepts_pipeline.cluster_candidates(candidates, embeddings)

        self.assertEqual(labels[0], labels[1])
        self.assertNotEqual(labels[0], labels[2])

    def test_form_concepts_deduplicates_names(self):
        """Одноимённые кластеры получают детерминированные суффиксы « (2)»."""
        candidates = [
            {"lemma": "aa", "surface": "aa", "upos": "NOUN",
             "sense_id": 1, "syntactic_context": "aa"},
            {"lemma": "bb", "surface": "bb", "upos": "NOUN",
             "sense_id": 1, "syntactic_context": "bb"},
            {"lemma": "aa", "surface": "aa", "upos": "NOUN",
             "sense_id": 2, "syntactic_context": "aa"},
            {"lemma": "cc", "surface": "cc", "upos": "NOUN",
             "sense_id": 2, "syntactic_context": "cc"},
        ]
        embeddings = np.eye(4, dtype=np.float32)
        labels = [10, 10, 20, 20]

        concepts, links = concepts_pipeline.form_concepts(candidates, embeddings, labels)

        self.assertEqual([c["name"] for c in concepts], ["aa", "aa (2)"])
        self.assertEqual([l["name"] for l in links], ["aa", "aa (2)"])
