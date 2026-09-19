import assert from 'node:assert/strict';
import test from 'node:test';
import {buildMealSuggestions, extractMealNamesFromHtml, summarizeDailyPlan, type MealItem} from '../lib/meal-planner';

test('meal planner extracts likely menu names and ignores section labels', ()=>{
  const html = `
    <div class="menu-day">
      <h3>Lunch</h3>
      <div class="menu-item">Grilled Chicken Bowl</div>
      <div class="menu-item">Broccoli & Rice</div>
      <div class="menu-item">Fruit Cup</div>
    </div>
  `;
  assert.deepEqual(extractMealNamesFromHtml(html), [
    'Grilled Chicken Bowl',
    'Broccoli & Rice',
    'Fruit Cup',
  ]);
});

test('meal planner ignores site copy and dining hall labels instead of treating them as food', ()=>{
  const html = `
    <a href="#main-content">Skip to main content</a>
    <h1>Find Your Fuel</h1>
    <p>Explore menus across all Virginia Tech dining locations. Fresh, daily updates right at your fingertips.</p>
    <div>West End at Cochrane Hall · 24P / 38C / 16F</div>
    <div>Dining Events (opens in a new tab)</div>
    <div class="menu-item">Grilled Chicken Bowl</div>
    <div class="menu-item">Veggie Rice Bowl</div>
  `;
  assert.deepEqual(extractMealNamesFromHtml(html), [
    'Grilled Chicken Bowl',
    'Veggie Rice Bowl',
  ]);
});

test('menu parser falls back when FoodPro returns only generic site copy', ()=>{
  const html = `
    <html>
      <body>
        <a href="#main-content">Skip to main content</a>
        <p>Explore menus across all Virginia Tech dining locations. Fresh, daily updates right at your fingertips.</p>
        <p>Virginia Polytechnic Institute and State University. All rights reserved.</p>
      </body>
    </html>
  `;
  const meals = extractMealNamesFromHtml(html);
  assert.deepEqual(meals, []);
});

test('meal planner keeps every valid menu item instead of truncating the results', ()=>{
  const html = `
    <div class="menu-item">Grilled Chicken Bowl</div>
    <div class="menu-item">Broccoli & Rice</div>
    <div class="menu-item">Fruit Cup</div>
    <div class="menu-item">Turkey Wrap</div>
    <div class="menu-item">Veggie Pasta</div>
    <div class="menu-item">Salmon Rice Plate</div>
    <div class="menu-item">Quinoa Salad</div>
    <div class="menu-item">Chicken Caesar Wrap</div>
    <div class="menu-item">Tofu Stir Fry</div>
    <div class="menu-item">Bean Burrito</div>
    <div class="menu-item">Oatmeal Bowl</div>
    <div class="menu-item">Yogurt Parfait</div>
    <div class="menu-item">Pesto Pasta</div>
    <div class="menu-item">Burger Slider</div>
    <div class="menu-item">Smoothie Bowl</div>
  `;

  const meals = buildMealSuggestions(html, 'D2 at Dietrick Hall');
  assert.equal(meals.length, 15);
  assert.deepEqual(
    meals.map((meal) => meal.name),
    [
      'Grilled Chicken Bowl',
      'Broccoli & Rice',
      'Fruit Cup',
      'Turkey Wrap',
      'Veggie Pasta',
      'Salmon Rice Plate',
      'Quinoa Salad',
      'Chicken Caesar Wrap',
      'Tofu Stir Fry',
      'Bean Burrito',
      'Oatmeal Bowl',
      'Yogurt Parfait',
      'Pesto Pasta',
      'Burger Slider',
      'Smoothie Bowl',
    ],
  );
});

test('daily macro totals add meal entries without double counting',()=>{
  const meals: MealItem[] = [
    {id:'1', name:'Grilled Chicken Bowl', calories: 540, protein: 42, carbs: 42, fat: 18, hall:'Dietrick', source:'fallback'},
    {id:'2', name:'Quinoa Salad', calories: 350, protein: 12, carbs: 32, fat: 16, hall:'Dietrick', source:'fallback'},
  ];
  assert.deepEqual(summarizeDailyPlan(meals), {
    calories: 890,
    protein: 54,
    carbs: 74,
    fat: 34,
  });
});
