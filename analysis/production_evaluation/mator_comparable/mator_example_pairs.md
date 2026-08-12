# Mator-comparable BERTScore — example pairs for eye-checking

Deterministic selection: lowest, median and highest scoring pair of each kind, so the examples bracket the observed range rather than flatter it.

Raw F1 is shown with its baseline-rescaled companion. The expected raw F1 for a pair of *unrelated* fluent English sentences at this layer is **0.8312** (the package's own rescaling baseline — an expectation over a random-pair corpus, not a hard floor: individual unrelated pairs land on both sides of it).


## Relevance of Response (participant turn vs. preceding moderator turn)

**lowest** — `fg3`, guide section 3, raw F1 **0.7827** (rescaled -0.288, length-matched 0.8329)

- *reference* (moderator, 19 words): Question 3. Do you think your gender influences what you eat? Tell us more about why or why not?
- *candidate* (participant, 466 words): I don't really think gender comes into it massively for me as a conscious thought, but like the minute we started getting a bit of summer and a bit of sun. Um, I had this idea in my head that I really want to get into offset smoking. Um, which if anyone doesn't know, it's like where you do like, you smoke like meat. So you put like a rack of ribs on like a barbecue and then you've got the, the thi […]

**median** — `macho_meals_fg3_demoonly_run01`, guide section 5, raw F1 **0.8248** (rescaled -0.038, length-matched 0.8475)

- *reference* (moderator, 59 words): Andrew — that distinction you've just made, between cooking for family and cooking for mates — I don't think we've heard that before. It's not just the routine, it's something about the risk being different. Does that land for anyone else? Is there something about doing it with your mates specifically that feels different from doing it with family?
- *candidate* (participant, 266 words): Yeah, Andrew's right. That's exactly it. With my old man, if the food's not great, it doesn't matter. He's just — he's glad I'm there, glad we're doing it. It's not about whether I'm a brilliant cook. It's about the fact that I'm trying. That I showed up and made an effort. But with the lads? It's different. Because they're mates, right? And there's this unspoken thing where — if you invite them r […]

**highest** — `fg3`, guide section 2, raw F1 **0.9145** (rescaled +0.493, length-matched 0.9145)

- *reference* (moderator, 9 words): Question 2. How do you decide what to eat?
- *candidate* (participant, 25 words): Um, how do you decide what to eat in relation to going out with friends or just generally how do we decide what to eat?


## Response similarity between participants (cross-speaker pair inside one guide section)

**lowest** — `fg3`, guide section 4, raw F1 **0.7784** (rescaled -0.313, length-matched 0.8071)

- *reference* (participant, 326 words): No, I was saying I was only, I was going to kind of kind of pick up the same point you've made. It is interesting when I think people make the sometimes they make that choice and they go I'm going to that because it's going to be better for my health and you you assume maybe the assumption that oh it's plant based it's got to be healthy. But it's what they've pumped into it to kind of get it to th […]
- *candidate* (participant, 3 words): Incompatibility, isn't it?

**median** — `macho_meals_fg3_demoonly_run03`, guide section 3, raw F1 **0.8452** (rescaled +0.083, length-matched 0.8363)

- *reference* (participant, 192 words): Yeah. I hear you. That's not small at all. And I think the thing that matters there is — you're not waiting for it to be perfect, are you? You're not saying, right, we'll do this when the commute gets better or when we're less tired or when everything's sorted. You're just doing it anyway. One night a week, you've decided it matters, and you're doing it. That's the opposite of what we were talking […]
- *candidate* (participant, 225 words): Yeah, that's... that's fair actually. John's right. I think I was being a bit glib saying I've never expected it to be my job, like I'm just naturally unbothered by it all. But listening to him break it down like that — aware it's happening without really questioning it — that's more honest, I reckon. Because it's not that I genuinely don't care or don't notice. I do notice when we've had takeaway […]

**highest** — `fg3`, guide section 4, raw F1 **1.0000** (rescaled +1.000, length-matched 1.0000)

- *reference* (participant, 1 words): Yeah.
- *candidate* (participant, 1 words): Yeah.

