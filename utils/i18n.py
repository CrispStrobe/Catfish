# utils/i18n.py

"""Internationalization support."""
import locale
from typing import Dict

class Translator:
    """Simple translation system for multilingual support."""
    
    def __init__(self):
        self.current_lang = 'en'
        self.translations = {
            'en': {
                # Main Interface
                'app_title': 'Universal File Search & Index Tool',
                'search_tab': 'Search Files',
                'manage_tab': 'Manage Indices',
                'duplicates_tab': 'Find Duplicates',
                'settings_tab': 'Settings',
                
                # Search Interface
                'search_criteria': 'Search Criteria',
                'name_pattern': 'Name (regex):',
                'name_examples': 'Examples: *.jpg, IMG_\\d+, (?i)vacation',
                'size_range': 'Size range:',
                'size_examples': ' (e.g., 1MB, 500KB)',
                'date_range': 'Date range:',
                'date_examples': ' (YYYY-MM-DD or \'today\', \'yesterday\')',
                'search_button': 'Search Files',
                'clear_button': 'Clear',
                'search_results': 'Search Results',
                'filename_col': 'Filename',
                'size_col': 'Size',
                'modified_col': 'Modified',
                'path_col': 'Full Path',
                'open_file': 'Open File',
                'open_folder': 'Open Folder',
                'copy_path': 'Copy Path',
                'export_results': 'Export Results',
                'close_button': 'Close',
                
                # Index Management
                'index_catalog': 'Index Catalog',
                'available_indices': 'Available Indices',
                'create_index': 'Create New Index',
                'refresh_indices': 'Refresh List',
                'delete_index': 'Delete Selected',
                'index_info': 'Index Information',
                'root_path': 'Root Path:',
                'file_count': 'Files:',
                'total_size': 'Total Size:',
                'created_date': 'Created:',
                'hash_method': 'Hash Method:',
                
                # Duplicate Detection
                'source_folder': 'Source Folder',
                'destination_folders': 'Destination Folders',
                'browse_button': 'Browse...',
                'add_folder': 'Add Folder',
                'remove_selected': 'Remove Selected',
                'clear_all': 'Clear All',
                'options': 'Options',
                'use_hash': 'Use file hashes for comparison',
                'reuse_indices': 'Reuse existing indices',
                'force_recreation': 'Force recreation of indices',
                'start_scan': 'Start Scan',
                'new_scan': 'New Scan',
                'exit_button': 'Exit',

                'method': 'Method',
                'found': 'Found',
                'files_with_duplicates': 'files with duplicates',
                'total_size': 'Total Size',
                
                # Results and Actions
                'duplicate_manager': 'Duplicate File Manager',
                'information': 'Information',
                'filter': 'Filter',
                'regex_filter': 'Regex filter:',
                'select_all_filtered': 'Select All Filtered',
                'deselect_all': 'Deselect All',
                'delete_selected': 'Delete Selected Files',
                'generate_script': 'Generate Script...',
                'index_col': 'Index',
                
                # Progress
                'initializing': 'Initializing...',
                'scanning_files': 'Scanning files...',
                'building_index': 'Building index...',
                'finding_duplicates': 'Finding duplicates...',
                'cancel_button': 'Cancel',
                
                # Messages
                'no_results': 'No search results to export.',
                'export_complete': 'Results exported to:\n{}',
                'export_error': 'Failed to export results:\n{}',
                'search_error': 'Search failed:\n{}',
                'no_duplicates': 'No duplicate files were found.\n\nWould you like to start a new scan?',
                'confirm_deletion': 'Are you sure you want to permanently delete {} files ({})?\n\nThis action CANNOT be undone.',
                'deletion_complete': 'Successfully deleted {} of {} selected files.',
                'script_generated': 'Deletion script was successfully saved to:\n{}',
                'ready_status': 'Ready to search {} indexed locations',
                'searching_status': 'Searching...',
                'found_status': 'Found {} files matching criteria',
                'selected_status': 'Selected: {} files ({:.1f} MB)',
                'no_selection_status': 'No files selected',
                'path_copied': 'Copied path to clipboard: {}',
                'select_source': 'Please select a source folder',
                'select_dest': 'Please add at least one destination folder',
                
                # Settings
                'language': 'Language:',
                'default_hash': 'Default Hash Algorithm:',
                'auto_load_indices': 'Auto-load indices on startup',
                'index_locations': 'Index Search Locations:',
                'add_location': 'Add Location',
                'remove_location': 'Remove Location',
                'apply_settings': 'Apply Settings',
                
                # Errors
                'error': 'Error',
                'file_not_found': 'File no longer exists:\n{}',
                'invalid_regex': 'Invalid regex pattern: {}',
                'invalid_size': 'Invalid size format: {}',
                'invalid_date': 'Invalid date format: {}',
                'scan_failed': 'Scan failed:\n{}',
                'no_indices': 'No search indices found.',
                'no_selection': 'No files are selected.',
                'duplicate_folder': 'This folder is already in the list.',
            },
            
            'de': {
                # Main Interface
                'app_title': 'Universelles Datei-Such- & Index-Tool',
                'search_tab': 'Dateien suchen',
                'manage_tab': 'Indices verwalten',
                'duplicates_tab': 'Duplikate finden',
                'settings_tab': 'Einstellungen',
                
                # Search Interface
                'search_criteria': 'Suchkriterien',
                'name_pattern': 'Name (regex):',
                'name_examples': 'Beispiele: *.jpg, IMG_\\d+, (?i)urlaub',
                'size_range': 'Größenbereich:',
                'size_examples': ' (z.B. 1MB, 500KB)',
                'date_range': 'Datumsbereich:',
                'date_examples': ' (JJJJ-MM-TT oder \'heute\', \'gestern\')',
                'search_button': 'Dateien suchen',
                'clear_button': 'Löschen',
                'search_results': 'Suchergebnisse',
                'filename_col': 'Dateiname',
                'size_col': 'Größe',
                'modified_col': 'Geändert',
                'path_col': 'Vollständiger Pfad',
                'open_file': 'Datei öffnen',
                'open_folder': 'Ordner öffnen',
                'copy_path': 'Pfad kopieren',
                'export_results': 'Ergebnisse exportieren',
                'close_button': 'Schließen',
                
                # Index Management
                'index_catalog': 'Index-Katalog',
                'available_indices': 'Verfügbare Indices',
                'create_index': 'Neuen Index erstellen',
                'refresh_indices': 'Liste aktualisieren',
                'delete_index': 'Ausgewählte löschen',
                'index_info': 'Index-Informationen',
                'root_path': 'Stammpfad:',
                'file_count': 'Dateien:',
                'total_size': 'Gesamtgröße:',
                'created_date': 'Erstellt:',
                'hash_method': 'Hash-Methode:',
                
                # Duplicate Detection
                'source_folder': 'Quellordner',
                'destination_folders': 'Zielordner',
                'browse_button': 'Durchsuchen...',
                'add_folder': 'Ordner hinzufügen',
                'remove_selected': 'Ausgewählte entfernen',
                'clear_all': 'Alle löschen',
                'options': 'Optionen',
                'use_hash': 'Dateihashes für Vergleich verwenden',
                'reuse_indices': 'Vorhandene Indices wiederverwenden',
                'force_recreation': 'Neuerststellung der Indices erzwingen',
                'start_scan': 'Scan starten',
                'new_scan': 'Neuer Scan',
                'exit_button': 'Beenden',

                'method': 'Methode',
                'found': 'Gefunden',
                'files_with_duplicates': 'Dateien mit Duplikaten',
                'total_size': 'Gesamtgröße',

                'selected': 'Ausgewählt',
                'source_duplicates': 'Quell-Duplikate',
                'destination_duplicates': 'Ziel-Duplikate', 
                'index_info': 'Index-Info',
                'last_updated': 'Zuletzt aktualisiert',
                'update_index': 'Index aktualisieren',
                'multiple_indices_found': 'Mehrere Indices gefunden',
                'select_indices_to_update': 'Wählen Sie zu aktualisierende Indices:',
                
                # Results and Actions
                'duplicate_manager': 'Duplikat-Dateiverwaltung',
                'information': 'Information',
                'filter': 'Filter',
                'regex_filter': 'Regex-Filter:',
                'select_all_filtered': 'Alle gefilterten auswählen',
                'deselect_all': 'Alle abwählen',
                'delete_selected': 'Ausgewählte Dateien löschen',
                'generate_script': 'Skript generieren...',
                'index_col': 'Index',
                
                # Progress
                'initializing': 'Initialisierung...',
                'scanning_files': 'Scanne Dateien...',
                'building_index': 'Erstelle Index...',
                'finding_duplicates': 'Suche Duplikate...',
                'cancel_button': 'Abbrechen',
                
                # Messages
                'no_results': 'Keine Suchergebnisse zum Exportieren.',
                'export_complete': 'Ergebnisse exportiert nach:\n{}',
                'export_error': 'Fehler beim Exportieren der Ergebnisse:\n{}',
                'search_error': 'Suche fehlgeschlagen:\n{}',
                'no_duplicates': 'Keine doppelten Dateien gefunden.\n\nMöchten Sie einen neuen Scan starten?',
                'confirm_deletion': 'Sind Sie sicher, dass Sie {} Dateien ({}) dauerhaft löschen möchten?\n\nDiese Aktion kann NICHT rückgängig gemacht werden.',
                'deletion_complete': 'Erfolgreich {} von {} ausgewählten Dateien gelöscht.',
                'script_generated': 'Löschskript wurde erfolgreich gespeichert unter:\n{}',
                'ready_status': 'Bereit zum Durchsuchen von {} Indizes',
                'searching_status': 'Suche läuft...',
                'found_status': '{} Dateien gefunden, die den Kriterien entsprechen',
                'selected_status': 'Ausgewählt: {} Dateien ({:.1f} MB)',
                'no_selection_status': 'Keine Dateien ausgewählt',
                'path_copied': 'Pfad in Zwischenablage kopiert: {}',
                'select_source': 'Bitte wählen Sie einen Quellordner',
                'select_dest': 'Bitte fügen Sie mindestens einen Zielordner hinzu',
                
                # Settings
                'language': 'Sprache:',
                'default_hash': 'Standard-Hash-Algorithmus:',
                'auto_load_indices': 'Indices beim Start automatisch laden',
                'index_locations': 'Index-Suchpfade:',
                'add_location': 'Pfad hinzufügen',
                'remove_location': 'Pfad entfernen',
                'apply_settings': 'Einstellungen anwenden',
                
                # Errors
                'error': 'Fehler',
                'file_not_found': 'Datei existiert nicht mehr:\n{}',
                'invalid_regex': 'Ungültiges Regex-Muster: {}',
                'invalid_size': 'Ungültiges Größenformat: {}',
                'invalid_date': 'Ungültiges Datumsformat: {}',
                'scan_failed': 'Scan fehlgeschlagen:\n{}',
                'no_indices': 'Keine Suchindices gefunden.',
                'no_selection': 'Keine Dateien ausgewählt.',
                'duplicate_folder': 'Dieser Ordner ist bereits in der Liste.',
            }
        }
        
        # Auto-detect system language
        try:
            system_lang = locale.getdefaultlocale()[0]
            if system_lang and system_lang.startswith('de'):
                self.current_lang = 'de'
        except:
            pass
    
    def set_language(self, lang_code: str):
        """Set the current language."""
        if lang_code in self.translations:
            self.current_lang = lang_code
    
    def get(self, key: str, *args) -> str:
        """Get translated string, with optional formatting."""
        text = self.translations[self.current_lang].get(key, key)
        if args:
            try:
                return text.format(*args)
            except:
                return text
        return text

# Global translator instance
translator = Translator()