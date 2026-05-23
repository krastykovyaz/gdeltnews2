import config

keyw = config.KEYWORDS
for kw in keyw:
    if kw in 'https://www.cnn.com/2026/02/06/tech/ai-entry-level-jobs-teens'.replace('-',''):
        print(kw)