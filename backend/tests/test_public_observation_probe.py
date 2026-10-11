from scripts.verify_public_observations import increased_failure


def sample(boot, at, count):
    return {'boot_id':boot,'at':at,'api':[{'name':'recheck_business_outcomes_total',
        'labels':{'reason':'model_unavailable'},'value':count}]}


def test_old_instance_final_flush_is_visible_during_rolling_deployment():
    before=[sample('old',10,2),sample('new',11,0)]
    old_flush=sample('old',13,3)
    after=[*before,old_flush,sample('new',14,0)]
    assert increased_failure(before,after,12)==old_flush


def test_counter_reset_is_scoped_to_boot_and_preexisting_errors_do_not_pass():
    before=[sample('old',10,8)]
    assert increased_failure(before,[sample('old',13,8)],12) is None
    new=sample('new',13,1)
    assert increased_failure(before,[new],12)==new
    assert increased_failure(before,[sample('new',11,1)],12) is None
