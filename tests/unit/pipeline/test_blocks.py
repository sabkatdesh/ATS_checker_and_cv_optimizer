from app.pipeline.blocks import data_block, user_message


def test_data_block_wraps_content() -> None:
    assert data_block("cv", "abc") == "<cv>\nabc\n</cv>"


def test_user_message_orders_blocks_then_task() -> None:
    msg = user_message([("job_description", "JD"), ("cv", "CV")], "Do the task.")
    assert msg == "<job_description>\nJD\n</job_description>\n<cv>\nCV\n</cv>\n\nDo the task."
