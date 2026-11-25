from django.db import migrations, models

# model_fit takes the landslide January job's attempts: the hazard's choices
# and its check constraint gain 'landslide' (the constraint is dropped and
# added again with the new list). No row changes, and fire's and flood's rows
# pass both lists. Applied to the shared database only after a backup and the
# user's go-ahead (landslide plan, Task 14). CheckConstraint(check=...) runs
# on Django 4.2 and 5.2, as 0012_model_fit does.


class Migration(migrations.Migration):

    dependencies = [
        ('history', '0013_landslide_purok_susceptibility_log'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='modelfit',
            name='model_fit_hazard',
        ),
        migrations.AlterField(
            model_name='modelfit',
            name='hazard',
            field=models.TextField(choices=[('fire', 'fire'), ('flood', 'flood'), ('landslide', 'landslide')],
                                   db_column='mfit_hazard'),
        ),
        migrations.AddConstraint(
            model_name='modelfit',
            constraint=models.CheckConstraint(check=models.Q(('hazard__in', ['fire', 'flood', 'landslide'])),
                                              name='model_fit_hazard'),
        ),
    ]
