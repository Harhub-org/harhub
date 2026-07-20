insert into public.categories (slug, name, description, icon) values
    ('games', 'Games', 'Games and interactive entertainment', 'gamepad-2'),
    ('tools', 'Tools', 'Developer and productivity tools', 'wrench'),
    ('utilities', 'Utilities', 'System utilities and helpers', 'settings'),
    ('cli', 'Command Line', 'CLI tools and terminal applications', 'terminal'),
    ('libraries', 'Libraries', 'Reusable libraries and frameworks', 'package'),
    ('multimedia', 'Multimedia', 'Audio, video, and image tools', 'film'),
    ('education', 'Education', 'Learning and educational apps', 'graduation-cap'),
    ('security', 'Security', 'Security, privacy, and networking tools', 'shield'),
    ('social', 'Social', 'Communication and social apps', 'message-circle'),
    ('other', 'Other', 'Everything else', 'box')
on conflict (slug) do nothing;