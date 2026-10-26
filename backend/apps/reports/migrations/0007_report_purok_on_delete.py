from django.db import migrations


def refk(table, column, target, on_delete):
    """
    Re-create the foreign key on table.column with the given ON DELETE rule,
    keeping its name. The key is found by its column, so the SQL works
    whatever name the database gave it.
    """
    return f"""
DO $$
DECLARE fk text;
BEGIN
    SELECT conname INTO fk FROM pg_constraint
     WHERE conrelid = '{table}'::regclass AND contype = 'f'
       AND conkey = ARRAY[(SELECT attnum FROM pg_attribute
                            WHERE attrelid = '{table}'::regclass AND attname = '{column}')]::smallint[];
    IF fk IS NULL THEN
        fk := '{table}_{column}_fk';
    ELSE
        EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', fk);
    END IF;
    EXECUTE format('ALTER TABLE {table} ADD CONSTRAINT %I FOREIGN KEY ({column}) REFERENCES {target} ON DELETE {on_delete} DEFERRABLE INITIALLY DEFERRED', fk);
END $$;
"""


class Migration(migrations.Migration):
    """
    Deleting a purok or a report must never fail on these keys.

    incr_prk_id is no longer in the model (0006), so Django stops clearing it
    when a purok is deleted, and copies of the app from before 0006 don't
    know the incident_report_purok table, so they don't clear its rows. The
    database does it instead, as it already does for the report's other
    keys (ON DELETE SET NULL): the old column is cleared, the link rows go.
    """

    dependencies = [
        ('reports', '0006_fire_report_puroks'),
    ]

    operations = [
        migrations.RunSQL(
            sql=refk('incident_report', 'incr_prk_id', 'purok(prk_id)', 'SET NULL'),
            reverse_sql=refk('incident_report', 'incr_prk_id', 'purok(prk_id)', 'NO ACTION'),
        ),
        migrations.RunSQL(
            sql=refk('incident_report_purok', 'incidentreport_id', 'incident_report(incr_id)', 'CASCADE'),
            reverse_sql=refk('incident_report_purok', 'incidentreport_id', 'incident_report(incr_id)', 'NO ACTION'),
        ),
        migrations.RunSQL(
            sql=refk('incident_report_purok', 'purok_id', 'purok(prk_id)', 'CASCADE'),
            reverse_sql=refk('incident_report_purok', 'purok_id', 'purok(prk_id)', 'NO ACTION'),
        ),
    ]
