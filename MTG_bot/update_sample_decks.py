import sqlite3

def update_sample_decks(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Clear existing sample decks to recreate them
    cursor.execute("DELETE FROM deck_cards WHERE deck_id IN (SELECT deck_id FROM decks WHERE deck_name IN ('mono_green_stomp', 'mono_red_aggro'))")
    cursor.execute("DELETE FROM decks WHERE deck_name IN ('mono_green_stomp', 'mono_red_aggro')")

    # Define 60-card sample decks
    decks_to_create = [
        ('mono_green_stomp', [('Forest', 24), ('Grizzly Bears', 36)]), # 60 cards
        ('mono_red_aggro', [('Mountain', 24), ('Goblin Arsonist', 32), ('Shock', 4)]) # 60 cards
    ]

    for deck_name, cards in decks_to_create:
        cursor.execute("INSERT OR IGNORE INTO decks (deck_name) VALUES (?)", (deck_name,))
        deck_id = cursor.execute("SELECT deck_id FROM decks WHERE deck_name = ?", (deck_name,)).fetchone()[0]

        for card_name, quantity in cards:
            cursor.execute("INSERT INTO deck_cards (deck_id, card_name, quantity) VALUES (?, ?, ?)", (deck_id, card_name, quantity))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    update_sample_decks("/home/sune/Documents/Projekt Projector/MTG_bot/data/mtg_cards.db")