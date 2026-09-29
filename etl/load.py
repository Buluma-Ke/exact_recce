from sqlalchemy import text

def load_data(engine, transformed_data_dict):
    """
    Executes transactional upserts into PostgreSQL based on transformed data.
    """
    print("\n--- Loading Data into Database ---")
    try:
        with engine.begin() as conn:
            for basename, rows in transformed_data_dict.items():
                print(f"Loading into DB: {basename}...")
                for row in rows:
                    # 1. Upsert Outlet
                    conn.execute(
                        text("""
                            INSERT INTO outlets (ke_number, outlet_name, physical_location, channel, division)
                            VALUES (:ke, :name, :loc, :chan, :div)
                            ON CONFLICT (outlet_name) DO UPDATE SET
                                ke_number = EXCLUDED.ke_number,
                                physical_location = EXCLUDED.physical_location,
                                channel = EXCLUDED.channel,
                                division = EXCLUDED.division
                        """),
                        {
                            "ke": row["ke_number"],
                            "name": row["outlet_name"],
                            "loc": row["physical_location"],
                            "chan": row["channel"],
                            "div": row["division"],
                        },
                    )

                    outlet_id = conn.execute(
                        text("SELECT outlet_id FROM outlets WHERE outlet_name = :name"),
                        {"name": row["outlet_name"]},
                    ).scalar()

                    # 2. Insert TMR Assignment if present
                    if row["tmr_name"]:
                        conn.execute(
                            text("""
                                INSERT INTO tmr_assignments (outlet_id, tmr_name, tmr_phone, physical_location, division)
                                VALUES (:oid, :name, :phone, :loc, :div)
                                ON CONFLICT DO NOTHING
                            """),
                            {
                                "oid": outlet_id,
                                "name": row["tmr_name"],
                                "phone": row["tmr_phone"],
                                "loc": row["physical_location"],
                                "div": row["division"],
                            },
                        )

                    # 3. Insert KDM Contact if present
                    if row["kdm_name"]:
                        existing_kdm = conn.execute(
                            text("SELECT kdm_id FROM kdm_contacts WHERE outlet_id = :oid AND kdm_name = :name"),
                            {"oid": outlet_id, "name": row["kdm_name"]},
                        ).scalar()

                        if not existing_kdm:
                            conn.execute(
                                text("""
                                    INSERT INTO kdm_contacts (outlet_id, kdm_name, kdm_phone, location)
                                    VALUES (:oid, :name, :phone, :loc)
                                """),
                                {
                                    "oid": outlet_id,
                                    "name": row["kdm_name"],
                                    "phone": row["kdm_phone"],
                                    "loc": row["physical_location"],
                                },
                            )

                    # 4. Upsert Recce Visits
                    conn.execute(
                        text("""
                            INSERT INTO recce_visits (
                                outlet_id, team_lead_name, team_lead_phone, date_of_recce,
                                date_of_activation, kick_off_time, raspberry_stock,
                                raspberry_price, comments, source_file
                            ) VALUES (
                                :oid, :tl_name, :tl_phone, :recce_date, :act_date,
                                :kickoff, :stock, :price, :comments, :file
                            )
                            ON CONFLICT (outlet_id, date_of_recce) DO UPDATE SET
                                team_lead_name = EXCLUDED.team_lead_name,
                                team_lead_phone = EXCLUDED.team_lead_phone,
                                date_of_activation = EXCLUDED.date_of_activation,
                                kick_off_time = EXCLUDED.kick_off_time,
                                raspberry_stock = EXCLUDED.raspberry_stock,
                                raspberry_price = EXCLUDED.raspberry_price,
                                comments = EXCLUDED.comments,
                                source_file = EXCLUDED.source_file
                        """),
                        {
                            "oid": outlet_id,
                            "tl_name": row["tl_name"],
                            "tl_phone": row["tl_phone"],
                            "recce_date": row["recce_date"],
                            "act_date": row["act_date"],
                            "kickoff": row["kickoff"],
                            "stock": row["stock"],
                            "price": row["price"],
                            "comments": row["comments"],
                            "file": row["source_file"],
                        },
                    )

        print("\nSync and database update completed successfully.")
        return True
    except Exception as e:
        print(f"\nError encountered during load: {e}")
        print("Transaction rolled back. No partial changes were saved.")
        return False
