from django.test import SimpleTestCase

from django.core.exceptions import FieldDoesNotExist
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
