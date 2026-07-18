.. _seaborn_gallery:

Seaborn-style distribution plots
================================

Distribution plots in the style of seaborn's example gallery, drawn with
simpleplot's own methods -- ``kdeplot``, ``ecdfplot``, ``rugplot`` and the
``inner``/``cut`` options on ``violinplot``. These take plain arrays rather
than a tidy dataframe, so there is no pandas or seaborn dependency; the
semantic-mapping API (``hue=``, ``FacetGrid``) is deliberately not replicated.
