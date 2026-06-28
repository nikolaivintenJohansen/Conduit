import pytest

from services.wallet.access_groups import (
    UnknownModelSlugError,
    create_access_group,
    delete_access_group,
    get_access_group,
    list_access_groups,
    update_access_group,
)


def test_create_and_list_access_group(db_session, model_catalog):
    created = create_access_group(
        db_session,
        name="mini-only",
        description="GPT-4o mini access",
        model_slugs=[model_catalog.slug],
    )

    assert created.group.name == "mini-only"
    assert created.model_slugs == [model_catalog.slug]

    groups = list_access_groups(db_session)
    ids = {group.group.id for group in groups}
    assert created.group.id in ids


def test_update_access_group_models(db_session, model_catalog):
    created = create_access_group(
        db_session,
        name="starter",
        model_slugs=[model_catalog.slug],
    )

    second_model = model_catalog
    updated = update_access_group(
        db_session,
        created.group.id,
        name="starter-v2",
        model_slugs=[second_model.slug],
    )
    assert updated is not None
    assert updated.group.name == "starter-v2"
    assert updated.model_slugs == [second_model.slug]


def test_create_access_group_rejects_unknown_model(db_session):
    with pytest.raises(UnknownModelSlugError):
        create_access_group(db_session, name="bad", model_slugs=["not-a-model"])


def test_delete_access_group(db_session, model_catalog):
    created = create_access_group(
        db_session,
        name="temp",
        model_slugs=[model_catalog.slug],
    )
    assert delete_access_group(db_session, created.group.id) is True
    assert get_access_group(db_session, created.group.id) is None
    assert delete_access_group(db_session, created.group.id) is False
