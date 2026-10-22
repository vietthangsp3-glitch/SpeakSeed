CREATE UNIQUE INDEX IF NOT EXISTS idx_library_words_one_published ON library_words(normalized_word) WHERE reviewed=1 AND normalized_word != '';
CREATE TRIGGER IF NOT EXISTS validate_library_word_insert BEFORE INSERT ON library_words WHEN NEW.reviewed=1 BEGIN
  SELECT CASE WHEN NEW.normalized_word='' OR NEW.meaning='' OR NEW.ipa='' OR NEW.pos='' OR NEW.stage NOT IN ('A0','A1','A2','B1','B2') OR NEW.topic='' OR NEW.example='' OR NEW.example_vi='' OR NEW.source='' THEN RAISE(ABORT, 'published vocabulary is incomplete') END;
END;
CREATE TRIGGER IF NOT EXISTS validate_library_word_update BEFORE UPDATE ON library_words WHEN NEW.reviewed=1 BEGIN
  SELECT CASE WHEN NEW.normalized_word='' OR NEW.meaning='' OR NEW.ipa='' OR NEW.pos='' OR NEW.stage NOT IN ('A0','A1','A2','B1','B2') OR NEW.topic='' OR NEW.example='' OR NEW.example_vi='' OR NEW.source='' THEN RAISE(ABORT, 'published vocabulary is incomplete') END;
END;
