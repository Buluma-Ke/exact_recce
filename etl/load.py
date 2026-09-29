import hashlib
from sqlalchemy import text


def calculate_file_sha256(file_path):
    """Calculates the SHA-256 hash of a file for duplicate tracking."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in f:
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def load_data(engine, transformed_data_dict, auto_create_outlets=True):
    """
    Loads transformed data into staging_activations and calls the database's
    native ingest_batch stored function.
    """
    print("\n--- Loading Data via Database Staging & Ingest Function ---")
    try:
        with engine.begin() as conn:
            for basename, rows in transformed_data_dict.items():
                if not rows:
                    continue

                print(f"Processing batch for file: {basename}...")

                # 1. Register or fetch the import batch
                # Assuming basename can serve as file_name, compute dummy or real hash if file path is available
                # Here we compute a pseudo-hash based on content if file path isn't passed directly,
                # or handle import_batches insertion:
                file_sha = hashlib.sha256(basename.encode()).hexdigest()

                # Insert into import_batches and get the generated batch id
                batch_res = conn.execute(
                    text("""
                        INSERT INTO import_batches (file_name, file_sha256, rows_total)
                        VALUES (:file_name, :file_sha, :rows_total)
                        ON CONFLICT (file_sha256) DO UPDATE SET
                            imported_at = now()
                        RETURNING id
                    """),
                    {
                        "file_name": basename,
                        "file_sha": file_sha,
                        "rows_total": len(rows),
                    },
                )
                batch_id = batch_res.scalar()

                # 2. Insert rows into staging_activations
                print(f"Staging {len(rows)} rows for batch ID {batch_id}...")
                for idx, row in enumerate(rows, start=1):
                    conn.execute(
                        text("""
                            INSERT INTO staging_activations (
                                batch_id, row_num, ke_number, outlet_name, physical_loc,
                                channel, division, kdm_name, kdm_phone, tmr_name, tmr_phone,
                                tl_name, tl_phone, recce_date, activation_date, kickoff_time,
                                stock_qty, stock_unit, price_can, price_bottle, comments
                            ) VALUES (
                                :batch_id, :row_num, :ke_number, :outlet_name, :physical_loc,
                                :channel, :division, :kdm_name, :kdm_phone, :tmr_name, :tmr_phone,
                                :tl_name, :tl_phone, :recce_date, :activation_date, :kickoff_time,
                                :stock_qty, :stock_unit, :price_can, :price_bottle, :comments
                            )
                        """),
                        {
                            "batch_id": batch_id,
                            "row_num": idx,
                            "ke_number": row.get("ke_number"),
                            "outlet_name": row.get("outlet_name"),
                            "physical_loc": row.get("physical_location"),
                            "channel": row.get("channel"),
                            "division": row.get("division"),
                            "kdm_name": row.get("kdm_name"),
                            "kdm_phone": row.get("kdm_phone"),
                            "tmr_name": row.get("tmr_name"),
                            "tmr_phone": row.get("tmr_phone"),
                            "tl_name": row.get("tl_name"),
                            "tl_phone": row.get("tl_phone"),
                            "recce_date": row.get("recce_date"),
                            "activation_date": row.get("act_date"),
                            "kickoff_time": row.get("kickoff"),
                            "stock_qty": row.get("stock"),
                            "stock_unit": row.get("stock_unit", "cases"),
                            "price_can": row.get("price_can"),
                            "price_bottle": row.get("price_bottle"),
                            "comments": row.get("comments"),
                        },
                    )

                # 3. Call the database ingest_batch function
                print(
                    f"Executing database ingest_batch for batch ID {batch_id}..."
                )
                result = conn.execute(
                    text(
                        "SELECT o_total, o_inserted, o_updated, o_unchanged, o_review FROM ingest_batch(:b_id, :auto_create)"
                    ),
                    {"b_id": batch_id, "auto_create": auto_create_outlets},
                ).fetchone()

                if result:
                    print(
                        f"Batch Results -> Total: {result.o_total} | Inserted: {result.o_inserted} | Updated: {result.o_updated} | Unchanged: {result.o_unchanged} | Sent to Review: {result.o_review}"
                    )

        print("\nSync and database staging ingestion completed successfully.")
        return True
    except Exception as e:
        print(f"\nError encountered during load: {e}")
        print("Transaction rolled back. No partial changes were saved.")
        return False
