"""Tests for the modding-digests parsers (no network / git required)."""

from pdx_syntax.scrapers.digest import (
    parse_effects_log,
    parse_triggers_log,
    parse_modifiers_log,
    parse_on_actions_log,
    parse_event_targets_log,
    parse_custom_localization_log,
    parse_data_types,
    _normalize_scopes,
    _detect_iterator,
)


# ---------------------------------------------------------------------------
# Fixture strings
# ---------------------------------------------------------------------------

EFFECTS_SAMPLE = """\
# Effect Documentation
## add_gold
Add gold to a country's treasury
**Supported Scopes**: country

## add_core
makes the location a core of the target country
**Supported Scopes**: location
**Supported Targets**: country

## add_army_tradition
Adds army tradition
**Supported Scopes**: country, international_organization
"""

TRIGGERS_SAMPLE = """\
# Trigger Documentation
## adm
The adm ability of the character
Traits: <, <=, =, !=, >, >=
Reads gamestate for all scopes.
**Supported Scopes**: character

## adjacent_to_owned_by
is the area/location adjacent to an area with a country's presence in it?
Traits: country tag/country scope
Reads gamestate for all scopes.
**Supported Scopes**: location, area
**Supported Targets**: country

## always
Checks if the assigned yes/no value is true
**Supported Scopes**: none
"""

MODIFIERS_SAMPLE = """\
Printing Modifier Definitions:
Tag: ai_require_cb_for_war, Categories: Country, , All,
Tag: army_logistics_distance, Categories: Unit, , All,
Tag: tax_modifier, Categories: Country, , All,
"""

ON_ACTIONS_SAMPLE = """\
On Action Documentation:

--------------------

yearly_country_pulse:
From Code: Yes
Expected Scope: country

--------------------

on_ruler_death_delhi_tombs_construction:
From Code: No
Expected Scope: country

--------------------

on_new_country_formed:
From Code: Yes
Expected Scope: none

--------------------
"""

EVENT_TARGETS_SAMPLE = """\
# Event Target Documentation
### capital
Unknown, add something in code registration
Input Scopes: country, dynasty, province, area
Output Scopes: location

### law_policy
gets the policy chosen for a particular law
Requires Data: yes
Input Scopes: country, international_organization
Output Scopes: policy

### global_var
A global link target
Global Link: yes

Event Targets Saved from Code:

saved_scope_alpha
saved_scope_beta
"""

CUSTOM_LOC_SAMPLE = """\
Custom Localization Documentation:

--------------------

GetDangerousRebelsFaction:

Scope: country
Random Valid: No

Entries:

$OTHER_REBEL_FACTION$
$RELIGIOUS_REBEL_FACTION$

--------------------

GetRandomFarmGoodName:

Scope: none
Random Valid: Yes

Entries:

$grain$
$livestock$
$wine$

--------------------

GetSimpleName:

Scope: location
Random Valid: No

Entries:

--------------------
"""

DATA_TYPES_SAMPLE = """\
GetGlobalVariable( Arg0 )
Description: Gets a global variable
Definition type: Global promote
Return type: Value

-----------------------

Country.GetCapital
Description: returns the capital of the country
Definition type: Promote
Return type: Location

-----------------------

MakeScope( Arg0, Arg1 )
Description: Creates a scope from arguments
Definition type: Global function
Return type: Scope

-----------------------

Country.GetName
Definition type: Function
Return type: String

-----------------------

CFixedPoint
Definition type: Type

-----------------------
"""


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParseEffectsLog:
    def test_basic_parsing(self):
        entries = parse_effects_log(EFFECTS_SAMPLE)
        assert len(entries) == 3

    def test_names(self):
        entries = parse_effects_log(EFFECTS_SAMPLE)
        names = [e["name"] for e in entries]
        assert "add_gold" in names
        assert "add_core" in names
        assert "add_army_tradition" in names

    def test_scopes_normalized(self):
        entries = parse_effects_log(EFFECTS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert by_name["add_gold"]["scope_type"] == "country"
        assert by_name["add_army_tradition"]["scope_type"] == "country, international_organization"

    def test_targets(self):
        entries = parse_effects_log(EFFECTS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert by_name["add_core"]["parameters"] == "country"
        assert by_name["add_gold"]["parameters"] == ""

    def test_description(self):
        entries = parse_effects_log(EFFECTS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert "gold" in by_name["add_gold"]["description"].lower()


class TestParseTriggersLog:
    def test_basic_parsing(self):
        entries = parse_triggers_log(TRIGGERS_SAMPLE)
        assert len(entries) == 3

    def test_traits_extracted(self):
        entries = parse_triggers_log(TRIGGERS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert "<, <=" in by_name["adm"]["traits"]
        assert "country tag" in by_name["adjacent_to_owned_by"]["traits"]

    def test_no_traits(self):
        entries = parse_triggers_log(TRIGGERS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert by_name["always"]["traits"] == ""

    def test_gamestate_line_filtered(self):
        entries = parse_triggers_log(TRIGGERS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert "Reads gamestate" not in by_name["adm"]["description"]

    def test_scopes_normalized(self):
        entries = parse_triggers_log(TRIGGERS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert by_name["adjacent_to_owned_by"]["scope_type"] == "location, area"


class TestParseModifiersLog:
    def test_basic_parsing(self):
        entries = parse_modifiers_log(MODIFIERS_SAMPLE)
        assert len(entries) == 3

    def test_names(self):
        entries = parse_modifiers_log(MODIFIERS_SAMPLE)
        names = [e["name"] for e in entries]
        assert "ai_require_cb_for_war" in names
        assert "army_logistics_distance" in names
        assert "tax_modifier" in names

    def test_categories_extracted(self):
        entries = parse_modifiers_log(MODIFIERS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert "Country" in by_name["ai_require_cb_for_war"]["categories"]
        assert "Unit" in by_name["army_logistics_distance"]["categories"]

    def test_all_category_filtered(self):
        entries = parse_modifiers_log(MODIFIERS_SAMPLE)
        for e in entries:
            assert "All" not in e["categories"]

    def test_header_skipped(self):
        entries = parse_modifiers_log(MODIFIERS_SAMPLE)
        names = [e["name"] for e in entries]
        assert "Printing Modifier Definitions" not in names


class TestParseOnActionsLog:
    def test_basic_parsing(self):
        entries = parse_on_actions_log(ON_ACTIONS_SAMPLE)
        assert len(entries) == 3

    def test_names(self):
        entries = parse_on_actions_log(ON_ACTIONS_SAMPLE)
        names = [e["name"] for e in entries]
        assert "yearly_country_pulse" in names
        assert "on_new_country_formed" in names

    def test_from_code(self):
        entries = parse_on_actions_log(ON_ACTIONS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert by_name["yearly_country_pulse"]["from_code"] is True
        assert by_name["on_ruler_death_delhi_tombs_construction"]["from_code"] is False

    def test_scope(self):
        entries = parse_on_actions_log(ON_ACTIONS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert by_name["yearly_country_pulse"]["scope_type"] == "country"
        assert by_name["on_new_country_formed"]["scope_type"] == "none"


class TestParseEventTargetsLog:
    def test_basic_parsing(self):
        entries = parse_event_targets_log(EVENT_TARGETS_SAMPLE)
        # 2 scoped + 1 global + 2 saved-from-code
        assert len(entries) == 5

    def test_scoped_entry(self):
        entries = parse_event_targets_log(EVENT_TARGETS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        cap = by_name["capital"]
        assert cap["input_scopes"] == "country, dynasty, province, area"
        assert cap["output_scopes"] == "location"

    def test_requires_data(self):
        entries = parse_event_targets_log(EVENT_TARGETS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert by_name["law_policy"]["requires_data"] is True
        assert by_name["capital"]["requires_data"] is False

    def test_global_link(self):
        entries = parse_event_targets_log(EVENT_TARGETS_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert by_name["global_var"]["global_link"] is True

    def test_saved_from_code(self):
        entries = parse_event_targets_log(EVENT_TARGETS_SAMPLE)
        names = [e["name"] for e in entries]
        assert "saved_scope_alpha" in names
        assert "saved_scope_beta" in names


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

class TestNormalizeScopes:
    def test_mixed_case(self):
        assert _normalize_scopes("Country, Location") == "country, location"

    def test_none(self):
        assert _normalize_scopes("none") == "none"

    def test_empty(self):
        assert _normalize_scopes("") == ""

    def test_trailing_spaces(self):
        assert _normalize_scopes("country  ") == "country"

    def test_multiple(self):
        assert _normalize_scopes("Country, Character, Location") == "country, character, location"


class TestDetectIterator:
    def test_any(self):
        is_iter, itype = _detect_iterator("any_country")
        assert is_iter is True
        assert itype == "trigger"

    def test_every(self):
        is_iter, itype = _detect_iterator("every_character")
        assert is_iter is True
        assert itype == "effect"

    def test_random(self):
        is_iter, itype = _detect_iterator("random_army")
        assert is_iter is True
        assert itype == "effect_random"

    def test_ordered(self):
        is_iter, itype = _detect_iterator("ordered_pop")
        assert is_iter is True
        assert itype == "effect_ordered"

    def test_non_iterator(self):
        is_iter, itype = _detect_iterator("add_gold")
        assert is_iter is False
        assert itype is None


class TestParseCustomLocalizationLog:
    def test_basic_parsing(self):
        entries = parse_custom_localization_log(CUSTOM_LOC_SAMPLE)
        assert len(entries) == 3

    def test_names(self):
        entries = parse_custom_localization_log(CUSTOM_LOC_SAMPLE)
        names = [e["name"] for e in entries]
        assert "GetDangerousRebelsFaction" in names
        assert "GetRandomFarmGoodName" in names
        assert "GetSimpleName" in names

    def test_scope(self):
        entries = parse_custom_localization_log(CUSTOM_LOC_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert by_name["GetDangerousRebelsFaction"]["scope"] == "country"
        assert by_name["GetRandomFarmGoodName"]["scope"] == "none"
        assert by_name["GetSimpleName"]["scope"] == "location"

    def test_random_valid(self):
        entries = parse_custom_localization_log(CUSTOM_LOC_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert by_name["GetDangerousRebelsFaction"]["random_valid"] is False
        assert by_name["GetRandomFarmGoodName"]["random_valid"] is True

    def test_entries(self):
        entries = parse_custom_localization_log(CUSTOM_LOC_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert "$RELIGIOUS_REBEL_FACTION$" in by_name["GetDangerousRebelsFaction"]["entries"]
        assert "$grain$" in by_name["GetRandomFarmGoodName"]["entries"]

    def test_empty_entries(self):
        entries = parse_custom_localization_log(CUSTOM_LOC_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        assert by_name["GetSimpleName"]["entries"] == ""


class TestParseDataTypes:
    def test_basic_parsing(self):
        entries = parse_data_types(DATA_TYPES_SAMPLE)
        assert len(entries) == 5

    def test_global_promote(self):
        entries = parse_data_types(DATA_TYPES_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        gv = by_name["GetGlobalVariable"]
        assert gv["definition_type"] == "Global promote"
        assert gv["return_type"] == "Value"
        assert gv["args"] == "Arg0"
        assert gv["parent_type"] is None
        assert gv["description"] == "Gets a global variable"

    def test_dot_notation_parent(self):
        entries = parse_data_types(DATA_TYPES_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        cap = by_name["Country.GetCapital"]
        assert cap["parent_type"] == "Country"
        assert cap["definition_type"] == "Promote"
        assert cap["return_type"] == "Location"
        assert cap["args"] is None

    def test_multiple_args(self):
        entries = parse_data_types(DATA_TYPES_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        ms = by_name["MakeScope"]
        assert ms["args"] == "Arg0, Arg1"
        assert ms["definition_type"] == "Global function"

    def test_no_description(self):
        entries = parse_data_types(DATA_TYPES_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        gn = by_name["Country.GetName"]
        assert gn["description"] == ""
        assert gn["definition_type"] == "Function"

    def test_type_no_return(self):
        entries = parse_data_types(DATA_TYPES_SAMPLE)
        by_name = {e["name"]: e for e in entries}
        fp = by_name["CFixedPoint"]
        assert fp["definition_type"] == "Type"
        assert fp["return_type"] == ""
        assert fp["parent_type"] is None
