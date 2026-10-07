# Generator schemas

AST discovery infers literal independent attribute ranges from the installed source.
Add a JSON file with `generator` equal to its fully qualified class and `parameters`
containing descriptions or full definitions. Existing inferred definitions can be
patched by name. New definitions require name, display_name, type, default, tooltip;
numeric controls also require minimum/maximum, enums require enum_values. Only
factory attribute overrides are currently supported. They are set before post_init.
Inspect source before defining an override; create_asset(**kwargs) does not imply
the generator consumes those keywords. Live modifier inputs use native RNA instead.

Run Discover after changing a schema. Validate generation at both ends of each range
and check dependent parameters. Do not expose sampling distributions as plain floats.
