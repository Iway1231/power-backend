from app.group_directory import infer_groups_for_address


def test_infer_group_for_shklo_and_kurortna():
    assert infer_groups_for_address("вул. Курортна смт. Шкло") == ["1.2"]


def test_infer_group_for_lis_and_okilky():
    assert infer_groups_for_address("с. Ліс та с. Окілки") == ["1.2"]
